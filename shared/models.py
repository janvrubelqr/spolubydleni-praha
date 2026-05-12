"""
Sdílené datové modely pro celý pipeline.

Každý scraper transformuje surová data z portálu do `ListingRecord`,
ten se pak ukládá do Supabase přes `repo.upsert_listing()`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ListingRecord(BaseModel):
    """Normalizovaný záznam o nabídce pronájmu."""

    # původ
    source: str                              # 'sreality', 'bezrealitky', 'flatio', ...
    source_id: str                           # ID na původním portálu
    url: str

    # obsah
    title: Optional[str] = None
    description: Optional[str] = None
    price_czk: Optional[int] = None
    price_includes_utilities: Optional[bool] = None
    deposit_czk: Optional[int] = None
    size_m2: Optional[float] = None
    rooms: Optional[str] = None              # '1+kk', '2+1', 'studio'
    furnished: Optional[bool] = None

    # lokalita
    district: Optional[str] = None           # 'Praha 2'
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    # syrový JSON pro audit
    raw: dict[str, Any] = Field(default_factory=dict)

    def location_wkt(self) -> Optional[str]:
        """PostGIS očekává WKT 'POINT(lon lat)'."""
        if self.lat is None or self.lon is None:
            return None
        return f"POINT({self.lon} {self.lat})"
