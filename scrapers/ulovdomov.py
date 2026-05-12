"""
UlovDomov scraper.

UlovDomov exposes the search data used by its frontend through a JSON API.
The public search filter for co-living/rooms is not stable from outside the
web app, so this scraper imports Prague flat rentals and lets the UI classify
shared housing as one of the filters.
"""
from __future__ import annotations

import logging
import math
import os
import re
import time
from typing import Any, Optional

import httpx

from shared.models import ListingRecord
from shared.repo import SupabaseRepo

log = logging.getLogger(__name__)

BASE_URL = "https://www.ulovdomov.cz"
API_URL = "https://ud.api.ulovdomov.cz/v1/offer/find"
PAGE_SIZE = 40

PRAGUE_BOUNDS = {
    "northEast": {"lat": 50.1775, "lng": 14.70686},
    "southWest": {"lat": 49.94198, "lng": 14.2246},
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/pronajem/praha",
}

SEARCH_BODY = {
    "offerType": "rent",
    "propertyType": "flat",
    "bounds": PRAGUE_BOUNDS,
}

DISPOSITION_TO_ROOMS = {
    "onepluskitchenette": "1+kk",
    "onepluskk": "1+kk",
    "oneplusone": "1+1",
    "twopluskitchenette": "2+kk",
    "twopluskk": "2+kk",
    "twoplusone": "2+1",
    "threepluskitchenette": "3+kk",
    "threepluskk": "3+kk",
    "threeplusone": "3+1",
    "fourpluskitchenette": "4+kk",
    "fourpluskk": "4+kk",
    "fourplusone": "4+1",
    "fivepluskitchenette": "5+kk",
    "fivepluskk": "5+kk",
    "fiveplusone": "5+1",
    "cohabitingstandaloneroom": "pokoj",
    "cohabitingsharedroom": "pokoj",
    "coliving": "pokoj",
    "atypical": "atypicky",
}

_DISTRICT_RE = re.compile(r"Praha\s*\d+", re.IGNORECASE)


def _fetch_page(client: httpx.Client, page: int) -> tuple[list[dict[str, Any]], int]:
    resp = client.post(
        API_URL,
        params={"page": page, "perPage": PAGE_SIZE, "sorting": "latest"},
        headers=HEADERS,
        json=SEARCH_BODY,
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()

    if not payload.get("success", False):
        raise ValueError(f"UlovDomov API returned an unsuccessful response: {payload}")

    data = payload.get("data") or {}
    offers = data.get("offers") or []
    extra = payload.get("extraData") or {}
    total_pages = int(extra.get("totalPages") or 0)

    return [offer for offer in offers if isinstance(offer, dict)], total_pages


def _money_value(value: Any) -> Optional[int]:
    if not isinstance(value, dict):
        return None
    if value.get("currency") not in (None, "CZK"):
        return None
    amount = value.get("value")
    return int(amount) if amount is not None else None


def _title(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        title = value.get("title")
        return str(title) if title else None
    return None


def _join_address(*parts: Optional[str]) -> Optional[str]:
    seen: set[str] = set()
    address_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        key = part.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            address_parts.append(part.strip())
    return ", ".join(address_parts) if address_parts else None


def _parse_rooms(disposition: Any) -> Optional[str]:
    if not disposition:
        return None
    key = re.sub(r"[^a-z0-9]", "", str(disposition).lower())
    return DISPOSITION_TO_ROOMS.get(key)


def _parse_district(*texts: Optional[str]) -> Optional[str]:
    for text in texts:
        if not text:
            continue
        match = _DISTRICT_RE.search(text)
        if match:
            return match.group(0).title()
    return None


def _offer_url(item: dict[str, Any]) -> str:
    absolute_url = item.get("absoluteUrl")
    if absolute_url:
        return str(absolute_url)

    source_id = item.get("id")
    seo = item.get("seo")
    if seo and source_id:
        return f"{BASE_URL}/inzerat/{seo}/{source_id}"

    return BASE_URL


def _to_record(item: dict[str, Any]) -> ListingRecord:
    source_id = str(item["id"])
    geo = item.get("geoCoordinates") or {}
    street = _title(item.get("street"))
    village_part = _title(item.get("villagePart"))
    village = _title(item.get("village"))
    address = _join_address(street, village_part, village)

    return ListingRecord(
        source="ulovdomov",
        source_id=source_id,
        url=_offer_url(item),
        title=item.get("title"),
        description=item.get("description"),
        price_czk=_money_value(item.get("rentalPrice")),
        deposit_czk=_money_value(item.get("depositPrice")),
        size_m2=float(item["area"]) if item.get("area") is not None else None,
        rooms=_parse_rooms(item.get("disposition")),
        district=_parse_district(address, item.get("title"), item.get("description")),
        address=address,
        lat=geo.get("lat"),
        lon=geo.get("lng"),
        raw=item,
    )


def _default_max_pages() -> int:
    value = os.getenv("ULOVDOMOV_MAX_PAGES")
    return int(value) if value else 50


def run(max_pages: Optional[int] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_pages = max_pages or _default_max_pages()
    repo = SupabaseRepo()
    run_id = repo.start_run("ulovdomov")

    seen = 0
    new = 0
    updated = 0
    active_ids: list[str] = []
    total_pages: Optional[int] = None
    pages_fetched = 0

    try:
        with httpx.Client(follow_redirects=True) as client:
            for page in range(1, max_pages + 1):
                log.info("UlovDomov page %d", page)
                offers, total_pages = _fetch_page(client, page)
                pages_fetched = page
                log.info("UlovDomov page %d: %d offers, total_pages=%d", page, len(offers), total_pages)

                if not offers:
                    break

                for item in offers:
                    try:
                        rec = _to_record(item)
                    except Exception:
                        log.exception("Failed to parse UlovDomov item %s", item.get("id"))
                        continue

                    active_ids.append(rec.source_id)
                    _, is_new = repo.upsert_listing(rec)
                    seen += 1
                    if is_new:
                        new += 1
                    else:
                        updated += 1

                    if seen % 50 == 0:
                        log.info("UlovDomov processed %d (new=%d, updated=%d)", seen, new, updated)

                if total_pages and page >= total_pages:
                    break

                time.sleep(1.0)

        delisted = 0
        complete_coverage = total_pages is not None and pages_fetched >= math.ceil(total_pages)
        if complete_coverage:
            delisted = repo.mark_delisted("ulovdomov", active_ids)
            log.info("Marked as delisted: %d", delisted)
        else:
            log.info("Skipping delisting because UlovDomov pagination is partial")

        repo.finish_run(
            run_id,
            status="ok",
            items_seen=seen,
            items_new=new,
            items_updated=updated,
        )
        log.info("Done UlovDomov: seen=%d, new=%d, updated=%d", seen, new, updated)

    except Exception as e:
        log.exception("UlovDomov scrape failed")
        repo.finish_run(run_id, status="error", items_seen=seen, error_message=str(e))
        raise


if __name__ == "__main__":
    run()
