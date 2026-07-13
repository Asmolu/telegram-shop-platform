import argparse
import asyncio
import json

from app.db.session import async_session_factory, dispose_database_engine
from app.modules.uploads.derivative_backfill import backfill_product_image_derivatives


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate missing product image derivatives. Dry-run is the default.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist derivative files and DB paths.",
    )
    parser.add_argument("--limit", type=int, default=100, help="Maximum rows to scan in one batch.")
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="Resume after this product_images.id.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with async_session_factory() as session:
        report = await backfill_product_image_derivatives(
            session,
            limit=args.limit,
            after_id=args.after_id,
            dry_run=not args.apply,
        )
    await dispose_database_engine()
    print(json.dumps({**report.__dict__, "dry_run": not args.apply}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
