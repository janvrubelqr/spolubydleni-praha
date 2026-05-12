"""
Sreality scraper.

Sreality.cz má veřejné JSON API (používá ho jejich vlastní frontend).
Endpoint: https://www.sreality.cz/api/cs/v2/estates
Filtrujeme: pronájem bytů v Praze.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Iterator, Optional

import httpx

from shared.models import ListingRecord
from shared.repo import SupabaseRepo

log = logging.getLogger(__name__)

BASE_URL = "https://www.sreality.cz/api/cs/v2/estates"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

LIST_PARAMS = {
    "category_main_cb": 2,
    "category_type_cb": 2,
    "locality_region_id": 10,
    "per_page": 60,
    "tms": int(time.time() * 1000),
}

_ROOMS_RE = re.compile(r"(\d\+(?:kk|\d))", re.IGNORECASE)


def _parse_rooms(name: str) -> Optional[str]:
    m = _ROOMS_RE.search(name or "")
    return m.group(1).lower() if m else None


def _parse_size(name: str) -> Optional[float]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", name or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _parse_district(locality: str) -> Optional[str]:
    if not locality:
        return None
    m = re.search(r"Praha\s+\d+", locality)
    return m.group(0) if m else None


def _to_record(item: dict) -> ListingRecord:
    hash_id = str(item["hash_id"])
    name = item.get("name", "")
    locality = item.get("locality", "")
    price = item.get("price_czk", {}).get("value_raw") or item.get("price")
    gps = item.get("gps") or {}
    url = f"https://www.sreality.cz/detail/pronajem/byt/-/-/{hash_id}"

    return ListingRecord(
        source="sreality",
        source_id=hash_id,
        url=url,
        title=name,
        price_czk=int(price) if price else None,
        size_m2=_parse_size(name),
        rooms=_parse_rooms(name),
        district=_parse_district(locality),
        address=locality,
        lat=gps.get("lat"),
        lon=gps.get("lon"),
        raw=item,
    )


def iter_listings(client: httpx.Client, max_pages: int = 50) -> Iterator[dict]:
    for page in range(1, max_pages + 1):
        params = {**LIST_PARAMS, "page": page}
        log.info("Sreality page %d", page)

        resp = client.get(BASE_URL, params=params, headers=HEADERS, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        estates = (data.get("_embedded") or {}).get("estates") or []
        if not estates:
            log.info("Žádné další položky, končím na stránce %d", page)
            break

        yield from estates
        time.sleep(1.0)


def run(max_pages: int = 50) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    repo = SupabaseRepo()
    run_id = repo.start_run("sreality")

    seen = 0
    new = 0
    updated = 0
    active_ids: list[str] = []

    try:
        with httpx.Client() as client:
            for item in iter_listings(client, max_pages=max_pages):
                try:
                    rec = _to_record(item)
                except Exception:
                    log.exception("Selhal parsing položky %s", item.get("hash_id"))
                    continue

                active_ids.append(rec.source_id)
                _, is_new = repo.upsert_listing(rec)
                seen += 1
                if is_new:
                    new += 1
                else:
                    updated += 1

                if seen % 50 == 0:
                    log.info("Zpracováno %d (new=%d, updated=%d)", seen, new, updated)

        delisted = repo.mark_delisted("sreality", active_ids)
        log.info("Označeno jako delisted: %d", delisted)

        repo.finish_run(
            run_id,
            status="ok",
            items_seen=seen,
            items_new=new,
            items_updated=updated,
        )
        log.info("Hotovo: seen=%d, new=%d, updated=%d", seen, new, updated)

    except Exception as e:
        log.exception("Scrape selhal")
        repo.finish_run(run_id, status="error", items_seen=seen, error_message=str(e))
        raise


if __name__ == "__main__":
    run()
