"""
Realingo scraper.

Realingo renders search results server-side into Next.js __NEXT_DATA__.
This scraper reads that embedded JSON from the Prague rentals search page and
normalizes only flat rental offers.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from typing import Any, Iterator, Optional

import httpx
from parsel import Selector

from shared.models import ListingRecord
from shared.repo import SupabaseRepo

log = logging.getLogger(__name__)

BASE_URL = "https://www.realingo.cz"
SEARCH_URL = f"{BASE_URL}/pronajem_reality/Praha/"
GRAPHQL_URL = f"{BASE_URL}/graphql"
PAGE_SIZE = 40
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}
GRAPHQL_HEADERS = {
    **HEADERS,
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": SEARCH_URL,
}

SEARCH_OFFER_QUERY = """
query SearchOffer($filter: OfferFilterInput!, $sort: OfferSort, $first: Int, $skip: Int) {
  searchOffer(filter: $filter, sort: $sort, first: $first, skip: $skip) {
    total
    items {
      id
      url
      purpose
      property
      createdAt
      category
      price {
        total
        canonical
        currency
      }
      area {
        main
        plot
      }
      photos {
        main
        list
      }
      location {
        address
        addressUrl
        locationPrecision
        latitude
        longitude
      }
    }
    location {
      id
      type
      url
      name
    }
  }
}
"""

CATEGORY_TO_ROOMS = {
    "FLAT1_KK": "1+kk",
    "FLAT11": "1+1",
    "FLAT2_KK": "2+kk",
    "FLAT21": "2+1",
    "FLAT3_KK": "3+kk",
    "FLAT31": "3+1",
    "FLAT4_KK": "4+kk",
    "FLAT41": "4+1",
    "FLAT5_KK": "5+kk",
    "FLAT51": "5+1",
}

_ROOMS_RE = re.compile(r"(\d\+kk|\d\+\d|studio)", re.IGNORECASE)
_DISTRICT_RE = re.compile(r"Praha\s*\d+", re.IGNORECASE)


def _normalize_url(href: Optional[str]) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def _parse_rooms(item: dict[str, Any]) -> Optional[str]:
    category = item.get("category")
    if category in CATEGORY_TO_ROOMS:
        return CATEGORY_TO_ROOMS[category]

    text = " ".join(
        str(value)
        for value in [
            item.get("url"),
            (item.get("location") or {}).get("address"),
        ]
        if value
    )
    match = _ROOMS_RE.search(text)
    return match.group(1).lower() if match else None


def _parse_district(address: Optional[str]) -> Optional[str]:
    if not address:
        return None
    match = _DISTRICT_RE.search(address)
    return match.group(0).title() if match else None


def _extract_next_data(html: str) -> dict[str, Any]:
    script = Selector(html).css("script#__NEXT_DATA__::text").get()
    if not script:
        raise ValueError("Realingo page does not contain __NEXT_DATA__")
    return json.loads(script)


def _extract_offers(html: str) -> list[dict[str, Any]]:
    data = _extract_next_data(html)
    try:
        offers = data["props"]["pageProps"]["store"]["offer"]["list"]["data"]
    except KeyError as exc:
        raise ValueError("Realingo __NEXT_DATA__ has an unexpected shape") from exc

    if not isinstance(offers, list):
        raise ValueError("Realingo offer list is not a list")
    return [offer for offer in offers if isinstance(offer, dict)]


def _fetch_page(client: httpx.Client, page: int) -> tuple[list[dict[str, Any]], int]:
    variables = {
        "filter": {
            "purpose": "RENT",
            "property": "FLAT",
            "address": "Praha",
        },
        "sort": "NEWEST",
        "first": PAGE_SIZE,
        "skip": (page - 1) * PAGE_SIZE,
    }
    resp = client.post(
        GRAPHQL_URL,
        headers=GRAPHQL_HEADERS,
        json={"query": SEARCH_OFFER_QUERY, "variables": variables},
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("errors"):
        raise ValueError(f"Realingo GraphQL returned errors: {payload['errors']}")

    result = (payload.get("data") or {}).get("searchOffer") or {}
    total = result.get("total") or 0
    items = result.get("items") or []
    return [item for item in items if isinstance(item, dict)], int(total)


def _to_record(item: dict[str, Any]) -> ListingRecord:
    location = item.get("location") or {}
    price = item.get("price") or {}
    area = item.get("area") or {}

    source_id = str(item["id"])
    url = _normalize_url(item.get("url"))
    address = location.get("address")
    rooms = _parse_rooms(item)
    size_m2 = area.get("main")

    title_parts = ["Byt"]
    if rooms:
        title_parts.append(rooms)
    if size_m2:
        title_parts.append(f"{size_m2:g} m2")
    if address:
        title_parts.append(address)

    return ListingRecord(
        source="realingo",
        source_id=source_id,
        url=url,
        title=", ".join(title_parts),
        price_czk=price.get("total") or price.get("canonical"),
        size_m2=float(size_m2) if size_m2 is not None else None,
        rooms=rooms,
        district=_parse_district(address),
        address=address,
        lat=location.get("latitude"),
        lon=location.get("longitude"),
        raw=item,
    )


def _is_target_offer(item: dict[str, Any]) -> bool:
    return (
        item.get("purpose") == "RENT"
        and item.get("property") == "FLAT"
        and item.get("id") is not None
        and item.get("url")
    )


def iter_listings(client: httpx.Client, max_pages: int = 100) -> Iterator[dict[str, Any]]:
    for page in range(1, max_pages + 1):
        log.info("Realingo GraphQL page %d", page)
        offers, total = _fetch_page(client, page)
        filtered = [offer for offer in offers if _is_target_offer(offer)]
        log.info("Realingo page %d: %d/%d offers", page, len(filtered), total)

        if not filtered:
            break

        yield from filtered

        if page >= math.ceil(total / PAGE_SIZE):
            break

        time.sleep(1.0)


def _default_max_pages() -> int:
    value = os.getenv("REALINGO_MAX_PAGES")
    return int(value) if value else 100


def run(max_pages: Optional[int] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    max_pages = max_pages or _default_max_pages()
    repo = SupabaseRepo()
    run_id = repo.start_run("realingo")

    seen = 0
    new = 0
    updated = 0
    active_ids: list[str] = []
    total_offers: Optional[int] = None
    pages_fetched = 0

    try:
        with httpx.Client(follow_redirects=True) as client:
            for page in range(1, max_pages + 1):
                log.info("Realingo GraphQL page %d", page)
                items, total_offers = _fetch_page(client, page)
                pages_fetched = page
                log.info("Realingo page %d: %d/%d offers", page, len(items), total_offers)

                if not items:
                    break

                for item in items:
                    if not _is_target_offer(item):
                        continue

                    try:
                        rec = _to_record(item)
                    except Exception:
                        log.exception("Failed to parse Realingo item %s", item.get("id"))
                        continue

                    active_ids.append(rec.source_id)
                    _, is_new = repo.upsert_listing(rec)
                    seen += 1
                    if is_new:
                        new += 1
                    else:
                        updated += 1

                    if seen % 50 == 0:
                        log.info("Realingo processed %d (new=%d, updated=%d)", seen, new, updated)

                if page >= math.ceil(total_offers / PAGE_SIZE):
                    break

                time.sleep(1.0)

        delisted = 0
        complete_coverage = total_offers is not None and pages_fetched >= math.ceil(total_offers / PAGE_SIZE)
        if complete_coverage:
            delisted = repo.mark_delisted("realingo", active_ids)
            log.info("Marked as delisted: %d", delisted)
        else:
            log.info("Skipping delisting because Realingo pagination is partial")

        repo.finish_run(
            run_id,
            status="ok",
            items_seen=seen,
            items_new=new,
            items_updated=updated,
        )
        log.info("Done Realingo: seen=%d, new=%d, updated=%d", seen, new, updated)

    except Exception as e:
        log.exception("Realingo scrape failed")
        repo.finish_run(run_id, status="error", items_seen=seen, error_message=str(e))
        raise


if __name__ == "__main__":
    run()
