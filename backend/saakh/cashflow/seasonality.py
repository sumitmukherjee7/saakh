"""Sector seasonal indices (calendar month Jan..Dec, mean = 1).

With only 12 months of statements, trend and seasonality cannot be separated
from the applicant's own data. We de-seasonalise with a sector prior, in
production this index is re-estimated monthly from the pooled, consented,
anonymised cash flows of each activity × region (see docs/DECISIONS.md, D-07).
"""
from __future__ import annotations

_RAW = {
    "tailoring": [1.2, 1.15, 0.9, 1.05, 1.1, 0.7, 0.65, 0.8, 0.9, 1.35, 1.4, 1.1],
    "fabrication": [1.05, 1.1, 1.3, 1.0, 1.0, 0.75, 0.65, 0.7, 0.85, 1.05, 1.1, 1.15],
    "dairy": [1.15, 1.1, 1.0, 0.85, 0.8, 0.85, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2],
    "leaf_plates": [1.2, 1.2, 1.0, 1.1, 1.15, 0.8, 0.6, 0.7, 0.9, 1.2, 1.3, 1.1],
    "food_processing": [1.1, 1.05, 1.0, 0.95, 0.95, 0.85, 0.85, 0.9, 1.0, 1.1, 1.15, 1.1],
    "street_food": [1.1, 1.05, 1.0, 0.95, 0.9, 0.8, 0.75, 0.8, 0.95, 1.1, 1.15, 1.15],
    "retail": [1.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.95, 0.95, 1.0, 1.1, 1.1, 1.0],
    "repair_services": [1.0, 1.0, 1.05, 1.05, 1.0, 0.95, 0.9, 0.9, 0.95, 1.05, 1.1, 1.05],
}


def _norm(v: list[float]) -> list[float]:
    m = sum(v) / len(v)
    return [x / m for x in v]


SEASONAL_INDEX: dict[str, list[float]] = {k: _norm(v) for k, v in _RAW.items()}
FLAT = [1.0] * 12


def index_for(activity: str | None) -> list[float]:
    return SEASONAL_INDEX.get(activity or "", FLAT)
