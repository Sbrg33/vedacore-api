#!/usr/bin/env python3
"""
Atlas Service

Loads and normalizes city atlas CSV files for location resolution.

Input files (no headers, utf-8-sig):
    - data/atlas/uscities.csv
    - data/atlas/world_cities_db.csv

Each row format:
    country, name, latitude, longitude, timezone

Normalization:
    - Trim whitespace, ensure floats for lat/lon, validate IANA timezone
    - For US rows with "City, ST" form, split to name + admin1
    - Generate stable ID: slug of country::name::admin1 (lowercased)

Outputs (optional; created by CLI build):
    - data/atlas/atlas_normalized.csv
    - data/atlas/index.json

This module is safe to import; data loads lazily on first use.
"""
from __future__ import annotations

import json
import re

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ATLAS_DIR = Path(__file__).resolve().parents[2] / "data" / "atlas"
USCITIES_FILE = ATLAS_DIR / "uscities.csv"
WORLD_CITIES_FILE = ATLAS_DIR / "world_cities_db.csv"
NORMALIZED_FILE = ATLAS_DIR / "atlas_normalized.csv"
INDEX_FILE = ATLAS_DIR / "index.json"


@dataclass
class AtlasEntry:
    id: str
    name: str
    country: str
    latitude: float
    longitude: float
    timezone: str
    admin1: str | None = None  # State/province
    elevation: float | None = None

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        # Do not expose None fields in public payloads
        return {k: v for k, v in d.items() if v is not None}


_ATLAS_LOADED = False
_ATLAS: list[AtlasEntry] = []
_INDEX_BY_ID: dict[str, AtlasEntry] = {}


def _strip_bom(s: str) -> str:
    # csv with utf-8-sig reader handles BOM at file start; this is a safety for names
    return s.lstrip("\ufeff").strip()


def _mk_id(country: str, name: str, admin1: str | None) -> str:
    # Stable lowercase slug separated by :: to avoid collisions
    base = f"{country.strip().lower()}::{name.strip().lower()}"
    if admin1:
        base += f"::{admin1.strip().lower()}"
    return re.sub(r"\s+", " ", base)


def _split_us_name(country: str, name: str) -> tuple[str, str | None]:
    if country.strip().lower() in {"united states", "usa", "us"} and "," in name:
        city, st = name.split(",", 1)
        return city.strip(), st.strip()
    return name.strip(), None


def _valid_timezone(tz: str) -> bool:
    try:
        ZoneInfo(tz)
        return True
    except Exception:
        return False


def _load_rows(path: Path) -> Iterable[tuple[str, str, float, float, str]]:
    import csv

    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            # Expect exactly 5 columns: country, name, lat, lon, tz
            if len(row) != 5:
                continue
            country, name, lat, lon, tz = [_strip_bom(x) for x in row]
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except Exception:
                continue
            if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
                continue
            if not _valid_timezone(tz):
                continue
            yield country, name, lat_f, lon_f, tz


def _normalize() -> list[AtlasEntry]:
    entries: list[AtlasEntry] = []
    for path in (USCITIES_FILE, WORLD_CITIES_FILE):
        for country, name, lat, lon, tz in _load_rows(path):
            name_clean, admin1 = _split_us_name(country, name)
            entry_id = _mk_id(country, name_clean, admin1)
            entries.append(
                AtlasEntry(
                    id=entry_id,
                    name=name_clean,
                    country=country,
                    latitude=lat,
                    longitude=lon,
                    timezone=tz,
                    admin1=admin1,
                )
            )
    return entries


def load_atlas(force: bool = False) -> None:
    global _ATLAS_LOADED, _ATLAS, _INDEX_BY_ID
    if _ATLAS_LOADED and not force:
        return
    entries = _normalize()
    _ATLAS = entries
    _INDEX_BY_ID = {e.id: e for e in entries}
    _ATLAS_LOADED = True


def get_by_id(entry_id: str) -> AtlasEntry | None:
    if not _ATLAS_LOADED:
        load_atlas()
    return _INDEX_BY_ID.get(entry_id)


def search(
    query: str,
    *,
    country: str | None = None,
    admin1: str | None = None,
    limit: int = 10,
) -> list[AtlasEntry]:
    if not _ATLAS_LOADED:
        load_atlas()
    q = query.strip().lower()
    c = country.strip().lower() if country else None
    a1 = admin1.strip().lower() if admin1 else None

    def match(entry: AtlasEntry) -> bool:
        if c and entry.country.strip().lower() != c:
            return False
        if a1 and (entry.admin1 or "").strip().lower() != a1:
            return False
        name_lc = entry.name.strip().lower()
        # Simple heuristic: startswith or substring match on name and "name, admin1"
        if q in name_lc or name_lc.startswith(q):
            return True
        if entry.admin1:
            combo = f"{name_lc}, {entry.admin1.strip().lower()}"
            if q in combo or combo.startswith(q):
                return True
        return False

    # Score: startswith gets priority over substring, then alphabetical by name
    scored: list[tuple[int, AtlasEntry]] = []
    for e in _ATLAS:
        if not match(e):
            continue
        name_lc = e.name.strip().lower()
        if name_lc.startswith(q):
            score = 0
        elif q in name_lc:
            score = 1
        else:
            score = 2
        scored.append((score, e))

    scored.sort(key=lambda t: (t[0], t[1].name))
    return [e for _, e in scored[: max(1, min(limit, 200))]]


def build_outputs() -> None:
    """Write normalized CSV and index JSON files."""
    load_atlas(force=True)
    # Write normalized CSV
    NORMALIZED_FILE.parent.mkdir(parents=True, exist_ok=True)
    import csv

    with NORMALIZED_FILE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "id",
                "name",
                "country",
                "admin1",
                "latitude",
                "longitude",
                "timezone",
            ]
        )
        for e in _ATLAS:
            writer.writerow(
                [
                    e.id,
                    e.name,
                    e.country,
                    e.admin1 or "",
                    f"{e.latitude:.6f}",
                    f"{e.longitude:.6f}",
                    e.timezone,
                ]
            )

    # Write index JSON keyed by id
    data = {e.id: e.to_public() for e in _ATLAS}
    INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    # Simple CLI: python -m app.services.atlas_service build
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build_outputs()
    else:
        # Default to build
        build_outputs()
