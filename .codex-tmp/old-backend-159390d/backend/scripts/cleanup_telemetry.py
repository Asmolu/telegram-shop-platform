from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import async_session_factory
from app.modules.analytics.service import AnalyticsService


async def _run() -> None:
    parser = argparse.ArgumentParser(description="Cleanup raw Mini App telemetry events")
    parser.add_argument("--days", type=int, default=None, help="Retention window in days")
    parser.add_argument("--batch-size", type=int, default=None, help="Maximum rows to delete")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete rows. Omit for dry-run.",
    )
    args = parser.parse_args()

    async with async_session_factory() as session:
        result = await AnalyticsService(session).cleanup_telemetry(
            retention_days=args.days,
            batch_size=args.batch_size,
            dry_run=not args.execute,
        )
    print(
        "telemetry cleanup "
        f"dry_run={result.dry_run} matched={result.matched} deleted={result.deleted} "
        f"cutoff={result.cutoff.isoformat()}"
    )


if __name__ == "__main__":
    asyncio.run(_run())
