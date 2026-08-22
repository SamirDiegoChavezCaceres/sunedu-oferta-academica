"""Show the quota-aware fetch logic.

    python scripts/fetch.py --estimate 4100000     # dry run, no network
    python scripts/fetch.py --path <dataset_path> --quota 1000   # live pull

The dry run needs no network: it shows why a 4.1M-row table (the size of the
national "postulantes" dataset) cannot be pulled through a 1000-request monthly
quota, and that the honest answer is the bulk microdata download.
"""

from __future__ import annotations

import argparse

from sunedu import QuotaExceeded, SuneduClient, estimate_requests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--estimate", type=int, help="dry run: rows to cost out")
    parser.add_argument("--path", help="dataset search endpoint path for a live pull")
    parser.add_argument("--quota", type=int, default=1000, help="monthly request quota")
    parser.add_argument("--page-size", type=int, default=1000)
    args = parser.parse_args()

    if args.estimate is not None:
        needed = estimate_requests(args.estimate, args.page_size)
        verdict = "fits" if needed <= args.quota else "does NOT fit -> use bulk microdata"
        print(f"{args.estimate:,} rows / {args.page_size} per page = "
              f"{needed:,} requests vs quota {args.quota:,}: {verdict}")
        return

    if not args.path:
        parser.error("pass --estimate for a dry run, or --path for a live pull")

    client = SuneduClient()
    try:
        rows = client.fetch_all(args.path, page_size=args.page_size, quota=args.quota)
        print(f"Fetched {len(rows):,} rows in {client.requests_made} requests.")
    except QuotaExceeded as exc:
        print(f"Refused: {exc}")


if __name__ == "__main__":
    main()
