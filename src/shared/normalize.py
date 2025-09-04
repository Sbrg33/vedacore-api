from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

NORMALIZATION_VERSION = "norm-2025-09-01.1"
EPHEMERIS_DATASET_VERSION = "swe-2.10.3"


def _delta_t_seconds(dt_utc: datetime) -> float:
    """Pinned ΔT model (constant 69.0s for determinism).

    Update when model changes; bump NORMALIZATION_VERSION in lockstep.
    """
    return 69.0


def utc_to_tt(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    return dt_utc + timedelta(seconds=_delta_t_seconds(dt_utc))


def round_coord(value: float, places: int = 6) -> float:
    return float(f"{value:.{places}f}")


@dataclass
class NormalizedInputs:
    datetime_utc: str  # ISO8601 Z
    datetime_tt: str  # ISO8601 Z
    lat: float
    lon: float
    alt_m: float | None
    normalization_version: str = NORMALIZATION_VERSION
    ephemeris_dataset_version: str = EPHEMERIS_DATASET_VERSION

    def as_dict(self) -> dict[str, Any]:
        d = {
            "datetime_utc": self.datetime_utc,
            "datetime_tt": self.datetime_tt,
            "lat": self.lat,
            "lon": self.lon,
            "alt_m": self.alt_m,
            "normalization_version": self.normalization_version,
            "ephemeris_dataset_version": self.ephemeris_dataset_version,
        }
        return d


def normalize_inputs(
    *,
    timestamp_iso: str,
    lat: float,
    lon: float,
    alt_m: float | None = None,
) -> NormalizedInputs:
    # Parse timestamp, assume Z if naive
    dt_utc = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00")).astimezone(UTC)
    dt_tt = utc_to_tt(dt_utc)
    return NormalizedInputs(
        datetime_utc=dt_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        datetime_tt=dt_tt.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        lat=round_coord(lat),
        lon=round_coord(lon),
        alt_m=alt_m,
    )


def content_addressed_key(
    *,
    prefix: str,
    normalized: NormalizedInputs,
    algo_version: str,
    api_version: str,
) -> str:
    payload = {
        **normalized.as_dict(),
        "algo_version": algo_version,
        "api_version": api_version,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"

