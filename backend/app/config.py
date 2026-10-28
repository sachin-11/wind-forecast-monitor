"""Runtime configuration, read from environment variables.

Everything has a sensible default so the app runs with zero configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True)
class Settings:
    # "elexon" -> live BMRS API, "sample" -> deterministic synthetic data (offline dev / tests)
    data_source: str = field(default_factory=lambda: os.getenv("DATA_SOURCE", "elexon").lower())
    elexon_base_url: str = field(default_factory=lambda: os.getenv("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"))
    http_timeout_s: float = field(default_factory=lambda: float(os.getenv("HTTP_TIMEOUT_S", "30")))
    cache_ttl_s: int = field(default_factory=lambda: int(os.getenv("CACHE_TTL_S", str(6 * 3600))))

    # Scope of the challenge: purchase decisions for deliveries in January 2026.
    window_start: datetime = field(default_factory=lambda: _parse_dt(os.getenv("WINDOW_START", "2026-01-01T00:00:00Z")))
    window_end: datetime = field(default_factory=lambda: _parse_dt(os.getenv("WINDOW_END", "2026-02-01T00:00:00Z")))

    # Forecast look-up rules
    max_horizon_h: int = 48  # UI slider range 0..48h
    max_lookback_h: int = 72  # oldest forecast we will ever consider for a target
    # Day-ahead decision cut-off: forecasts published before this local (UK) time on D-1
    # are the ones a trader could actually use for delivery day D.
    decision_cutoff_local: str = field(default_factory=lambda: os.getenv("DECISION_CUTOFF", "09:00"))
    local_tz: str = "Europe/London"
    # Trailing window used to calibrate the causal bias correction and uncertainty band.
    correction_days: int = field(default_factory=lambda: int(os.getenv("CORRECTION_DAYS", "14")))

    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip())
    )


settings = Settings()
