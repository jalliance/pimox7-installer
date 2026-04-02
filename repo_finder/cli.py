import argparse
import asyncio
import os
import sys

from .parser import parse_repo_input
from .core import run_search
from .report import print_report, print_json
from .downloader import offer_download


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="repo-finder",
        description="Find source code for deleted/taken-down git repositories.",
        epilog="Examples:\n"
        "  python -m repo_finder octocat/hello-world\n"
        "  python -m repo_finder https://github.com/octocat/hello-world --json\n"
        "  python -m repo_finder https://gitlab.com/user/project\n"
        "  python -m repo_finder https://bitbucket.org/owner/repo -d ./recovered\n"
        "  python -m repo_finder octocat/hello-world --sources forks swh\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "repo",
        help="Repo as 'owner/repo' (assumes GitHub) or full URL from any git host",
    )
    p.add_argument(
        "--token",
        help="GitHub personal access token (or set GITHUB_TOKEN env var)",
    )
    p.add_argument(
        "--download",
        "-d",
        metavar="DIR",
        help="Download/clone best available copy to DIR",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    p.add_argument(
        "--sources",
        nargs="+",
        metavar="SRC",
        help="Only search specific sources: forks, mirrors, wayback, swh, packages, google",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    return p


def main():
    args = build_parser().parse_args()

    try:
        info = parse_repo_input(args.repo)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    token = args.token or os.environ.get("GITHUB_TOKEN")

    results = asyncio.run(
        run_search(
            info,
            token=token,
            source_filter=args.sources,
            timeout=args.timeout,
        )
    )

    if args.json:
        print_json(results)
    else:
        print_report(results, info)

    if args.download:
        offer_download(results, args.download)
