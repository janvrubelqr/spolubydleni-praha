"""
Repository nad Supabase — encapsuluje všechny zápisy.

Použití:
    repo = SupabaseRepo()
    run_id = repo.start_run('sreality')
    for record in scrape():
        repo.upsert_listing(record)
    repo.finish_run(run_id, status='ok', items_seen=...)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from supabase import Client, create_client

from shared.models import ListingRecord


class SupabaseRepo:
    def __init__(self, url: Optional[str] = None, service_key: Optional[str] = None):
        url = url or os.environ["SUPABASE_URL"]
        service_key = service_key or os.environ["SUPABASE_SERVICE_KEY"]
        self.client: Client = create_client(url, service_key)

    # -----------------------------------------------------------------
    # scrape_runs
    # -----------------------------------------------------------------
    def start_run(self, source: str) -> int:
        res = (
            self.client.table("scrape_runs")
            .insert({"source": source, "status": "running"})
            .execute()
        )
        return res.data[0]["id"]

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        items_seen: int = 0,
        items_new: int = 0,
        items_updated: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        self.client.table("scrape_runs").update(
            {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "items_seen": items_seen,
                "items_new": items_new,
                "items_updated": items_updated,
                "error_message": error_message,
            }
        ).eq("id", run_id).execute()

    # -----------------------------------------------------------------
    # listings
    # -----------------------------------------------------------------
    def upsert_listing(self, rec: ListingRecord) -> tuple[str, bool]:
        """
        Vloží nebo aktualizuje záznam.
        Vrací (listing_id, is_new).
        """
        # zjistíme, jestli už existuje
        existing = (
            self.client.table("listings")
            .select("id, price_czk")
            .eq("source", rec.source)
            .eq("source_id", rec.source_id)
            .limit(1)
            .execute()
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        payload = {
            "source": rec.source,
            "source_id": rec.source_id,
            "url": rec.url,
            "title": rec.title,
            "description": rec.description,
            "price_czk": rec.price_czk,
            "price_includes_utilities": rec.price_includes_utilities,
            "deposit_czk": rec.deposit_czk,
            "size_m2": rec.size_m2,
            "rooms": rec.rooms,
            "furnished": rec.furnished,
            "district": rec.district,
            "address": rec.address,
            "location": rec.location_wkt(),  # WKT — Postgres si přebere přes geography(point)
            "scraped_at": now_iso,
            "last_seen_at": now_iso,
            "delisted_at": None,
            "raw": rec.raw,
        }

        if existing.data:
            listing_id = existing.data[0]["id"]
            old_price = existing.data[0]["price_czk"]

            self.client.table("listings").update(payload).eq("id", listing_id).execute()

            # pokud se cena změnila, zaznamenat
            if rec.price_czk is not None and rec.price_czk != old_price:
                self.client.table("price_history").insert(
                    {"listing_id": listing_id, "price_czk": rec.price_czk}
                ).execute()

            return listing_id, False
        else:
            # nový — first_seen_at se nastaví defaultem
            res = self.client.table("listings").insert(payload).execute()
            listing_id = res.data[0]["id"]

            if rec.price_czk is not None:
                self.client.table("price_history").insert(
                    {"listing_id": listing_id, "price_czk": rec.price_czk}
                ).execute()

            return listing_id, True

    def mark_delisted(self, source: str, active_source_ids: list[str]) -> int:
        """
        Po skončení běhu označí jako delisted ty inzeráty,
        které už ve výsledcích nejsou.
        """
        if not active_source_ids:
            return 0

        # Supabase nemá NOT IN na velkém listu pohodlně,
        # ale .not_.in_ funguje pro stovky položek
        res = (
            self.client.table("listings")
            .update({"delisted_at": datetime.now(timezone.utc).isoformat()})
            .eq("source", source)
            .is_("delisted_at", "null")
            .not_.in_("source_id", active_source_ids)
            .execute()
        )
        return len(res.data) if res.data else 0
