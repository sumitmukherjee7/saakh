"""Expire lapsed consents and delete their data, run from cron in multi-worker deployments.

    python -m saakh.sweep

The API process also runs this every SAAKH_EXPIRY_SWEEP_SECONDS (default 300).
"""
from __future__ import annotations

from .agent import runtime as R


def main() -> None:
    done = R.sweep_due()
    print(f"expiry sweep: {len(done)} case(s) processed")


if __name__ == "__main__":
    main()
