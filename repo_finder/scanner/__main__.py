"""CLI for the repo scanner.

Usage:
    python -m repo_finder.scanner discover [--min-stars 10] [--start 2020-01-01]
    python -m repo_finder.scanner scan [--limit 1000] [--quiet]
    python -m repo_finder.scanner add <url> [<url>...]
    python -m repo_finder.scanner list [--removed | --alive] [--limit 50]
    python -m repo_finder.scanner import <file>
    python -m repo_finder.scanner stats
"""

import argparse
import asyncio
import os
import sys

from .db import init_db, add_repo, list_repos, get_stats, get_discover_state
from .check import run_scan
from .discover import run_discover
from ..parser import parse_repo_input


def cmd_discover(args):
    token = args.token or os.environ.get("GITHUB_TOKEN")
    asyncio.run(
        run_discover(
            min_stars=args.min_stars,
            token=token,
            start_date=args.start,
            end_date=args.end,
        )
    )


def cmd_add(args):
    init_db()
    for url in args.urls:
        try:
            info = parse_repo_input(url)
            repo_id = add_repo(info.owner, info.repo, info.platform, info.origin_url)
            print(f"  Added: {info.origin_url} (id={repo_id})")
        except ValueError as e:
            print(f"  Error: {e}", file=sys.stderr)


def cmd_scan(args):
    token = args.token or os.environ.get("GITHUB_TOKEN")
    asyncio.run(
        run_scan(
            token=token,
            batch_limit=args.limit,
            quiet=args.quiet,
        )
    )


def cmd_list(args):
    init_db()
    status = None
    if args.removed:
        status = "removed"
    elif args.alive:
        status = "alive"

    repos = list_repos(status=status, limit=args.limit)
    if not repos:
        print("No repos found.")
        return

    for r in repos:
        marker = "X" if r["status"] == "removed" else "."
        stars = f" ({r.get('stars', 0)} stars)" if r.get("stars") else ""
        removed_info = f" removed {r['removed_at'][:10]}" if r["removed_at"] else ""
        checked_info = f" checked {r['last_checked'][:10]}" if r["last_checked"] else ""
        print(f"  [{marker}] {r['origin_url']}{stars}{removed_info}{checked_info}")

    stats = get_stats()
    print(f"\n  Total: {stats['total']} | Alive: {stats['alive']} | Removed: {stats['removed']}")


def cmd_import(args):
    init_db()
    count = 0
    with open(args.file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                info = parse_repo_input(line)
                add_repo(info.owner, info.repo, info.platform, info.origin_url)
                count += 1
            except ValueError as e:
                print(f"  Skipping {line!r}: {e}", file=sys.stderr)
    print(f"Imported {count} repos.")


def cmd_stats(args):
    init_db()
    stats = get_stats()
    last_crawled = get_discover_state("last_crawled_date")
    print(f"Watched repos: {stats['total']}")
    print(f"  Alive:   {stats['alive']}")
    print(f"  Removed: {stats['removed']}")
    if last_crawled:
        print(f"  Discovery crawled through: {last_crawled}")


def main():
    p = argparse.ArgumentParser(
        prog="repo-scanner",
        description="Discover and monitor GitHub repos, detect when they get removed.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # discover
    disc_p = sub.add_parser(
        "discover",
        help="Crawl GitHub for all repos with >N stars (resumable)",
    )
    disc_p.add_argument("--min-stars", type=int, default=10, help="Minimum stars (default: 10)")
    disc_p.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN)")
    disc_p.add_argument("--start", help="Start date (YYYY-MM-DD), overrides resume point")
    disc_p.add_argument("--end", help="End date (YYYY-MM-DD), defaults to today")
    disc_p.set_defaults(func=cmd_discover)

    # scan
    scan_p = sub.add_parser("scan", help="Check watched repos for removal")
    scan_p.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN)")
    scan_p.add_argument("--limit", type=int, default=1000, help="Max repos to check per run (default: 1000)")
    scan_p.add_argument("--quiet", "-q", action="store_true", help="Only print removals")
    scan_p.set_defaults(func=cmd_scan)

    # add
    add_p = sub.add_parser("add", help="Add repos to watch list")
    add_p.add_argument("urls", nargs="+", help="Repo URLs or owner/repo")
    add_p.set_defaults(func=cmd_add)

    # list
    list_p = sub.add_parser("list", help="List watched repos")
    list_g = list_p.add_mutually_exclusive_group()
    list_g.add_argument("--removed", action="store_true", help="Show only removed repos")
    list_g.add_argument("--alive", action="store_true", help="Show only alive repos")
    list_p.add_argument("--limit", type=int, default=50, help="Max repos to show (default: 50)")
    list_p.set_defaults(func=cmd_list)

    # import
    import_p = sub.add_parser("import", help="Import repos from a file (one per line)")
    import_p.add_argument("file", help="File with repo URLs, one per line")
    import_p.set_defaults(func=cmd_import)

    # stats
    stats_p = sub.add_parser("stats", help="Show scan statistics")
    stats_p.set_defaults(func=cmd_stats)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
