"""Discover GitHub repos with >N stars using the Search API.

The GitHub Search API returns at most 1000 results per query. To enumerate
all repos above a star threshold, we partition by creation date ranges and
subdivide any range that exceeds the 1000-result cap.

Progress is saved to the database so the crawl can be resumed at any time.
"""

import asyncio
import sys
from datetime import date, timedelta

import httpx

from .db import init_db, add_repos_bulk, get_discover_state, set_discover_state

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
MAX_RESULTS_PER_QUERY = 1000
PER_PAGE = 100
# GitHub Search rate limit: 30 req/min authenticated, 10/min unauthenticated
SEARCH_DELAY = 2.5  # seconds between requests (safe for authenticated)


async def _search_page(
    session: httpx.AsyncClient,
    query: str,
    page: int,
) -> dict | None:
    """Fetch one page of search results. Returns parsed JSON or None on failure."""
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": str(PER_PAGE),
        "page": str(page),
    }
    try:
        resp = await session.get(GITHUB_SEARCH_URL, params=params, timeout=30)
        if resp.status_code == 422:
            # Validation error (e.g. date out of range)
            return None
        if resp.status_code == 403:
            # Rate limited — wait and retry
            retry_after = resp.headers.get("Retry-After", "60")
            wait = int(retry_after)
            print(f"  Rate limited, waiting {wait}s...", file=sys.stderr)
            await asyncio.sleep(wait)
            resp = await session.get(GITHUB_SEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        print(f"  Search error: {e}", file=sys.stderr)
        return None


def _parse_repos(items: list[dict]) -> list[dict]:
    """Extract repo info from GitHub search result items."""
    repos = []
    for item in items:
        owner = item.get("owner", {}).get("login", "")
        repo = item.get("name", "")
        if not owner or not repo:
            continue
        repos.append({
            "owner": owner,
            "repo": repo,
            "platform": "github",
            "origin_url": f"https://github.com/{owner}/{repo}",
            "stars": item.get("stargazers_count", 0),
        })
    return repos


async def _crawl_date_range(
    session: httpx.AsyncClient,
    min_stars: int,
    start: date,
    end: date,
    db_path: str | None = None,
) -> int:
    """Crawl all repos with >min_stars created in [start, end]. Returns count added."""
    date_range = f"{start.isoformat()}..{end.isoformat()}"
    query = f"stars:>{min_stars} created:{date_range}"

    # First page to get total_count
    data = await _search_page(session, query, page=1)
    if not data:
        return 0

    total_count = data.get("total_count", 0)

    if total_count == 0:
        return 0

    # If too many results for this range, subdivide
    if total_count > MAX_RESULTS_PER_QUERY:
        if start == end:
            # Single day with >1000 repos — subdivide by star ranges instead
            return await _crawl_star_subdivide(
                session, min_stars, start, db_path=db_path
            )

        mid = start + (end - start) // 2
        count = 0
        count += await _crawl_date_range(session, min_stars, start, mid, db_path)
        count += await _crawl_date_range(session, min_stars, mid + timedelta(days=1), end, db_path)
        return count

    # Crawl all pages
    total_added = 0
    items = data.get("items", [])
    repos = _parse_repos(items)
    total_added += add_repos_bulk(repos, db_path)

    pages = (total_count + PER_PAGE - 1) // PER_PAGE
    pages = min(pages, MAX_RESULTS_PER_QUERY // PER_PAGE)  # API cap

    for page in range(2, pages + 1):
        await asyncio.sleep(SEARCH_DELAY)
        data = await _search_page(session, query, page=page)
        if not data:
            break
        items = data.get("items", [])
        if not items:
            break
        repos = _parse_repos(items)
        total_added += add_repos_bulk(repos, db_path)

    return total_added


async def _crawl_star_subdivide(
    session: httpx.AsyncClient,
    min_stars: int,
    day: date,
    db_path: str | None = None,
) -> int:
    """For a single day with >1000 repos, subdivide by star count ranges."""
    date_str = day.isoformat()
    total_added = 0

    # Binary search for star count boundaries
    # Start with large ranges and subdivide
    ranges = _make_star_ranges(min_stars + 1, 500000)

    for low, high in ranges:
        if high:
            query = f"stars:{low}..{high} created:{date_str}"
        else:
            query = f"stars:>={low} created:{date_str}"

        data = await _search_page(session, query, page=1)
        await asyncio.sleep(SEARCH_DELAY)
        if not data:
            continue

        total_count = data.get("total_count", 0)
        if total_count == 0:
            continue

        items = data.get("items", [])
        repos = _parse_repos(items)
        total_added += add_repos_bulk(repos, db_path)

        pages = min(
            (total_count + PER_PAGE - 1) // PER_PAGE,
            MAX_RESULTS_PER_QUERY // PER_PAGE,
        )
        for page in range(2, pages + 1):
            await asyncio.sleep(SEARCH_DELAY)
            page_data = await _search_page(session, query, page=page)
            if not page_data:
                break
            items = page_data.get("items", [])
            if not items:
                break
            repos = _parse_repos(items)
            total_added += add_repos_bulk(repos, db_path)

    return total_added


def _make_star_ranges(min_stars: int, max_stars: int) -> list[tuple[int, int | None]]:
    """Generate star count ranges that keep each bucket under 1000 results.
    Uses exponential ranges: 11-20, 21-50, 51-100, 101-500, 501-1000, ...
    """
    ranges = []
    boundaries = [
        min_stars, 20, 50, 100, 200, 500, 1000, 2000, 5000,
        10000, 50000, 100000, max_stars,
    ]
    # Deduplicate and sort
    boundaries = sorted(set(b for b in boundaries if b >= min_stars))

    for i in range(len(boundaries) - 1):
        ranges.append((boundaries[i], boundaries[i + 1]))
    # Final open-ended range
    if boundaries:
        ranges.append((boundaries[-1] + 1, None))

    return ranges


async def run_discover(
    min_stars: int = 10,
    token: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: str | None = None,
):
    """Main discovery crawl. Enumerates all GitHub repos with >min_stars.

    Saves progress so it can be resumed. Uses date-range partitioning
    to work around the 1000-result search API cap.
    """
    init_db(db_path)

    # Determine date range
    today = date.today()

    if end_date:
        crawl_end = date.fromisoformat(end_date)
    else:
        crawl_end = today

    if start_date:
        crawl_start = date.fromisoformat(start_date)
    else:
        # Resume from last crawled date, or start from GitHub's beginning
        last = get_discover_state("last_crawled_date", db_path=db_path)
        if last:
            crawl_start = date.fromisoformat(last) + timedelta(days=1)
        else:
            crawl_start = date(2008, 1, 1)  # GitHub launched 2008

    if crawl_start > crawl_end:
        print(f"Already crawled up to {crawl_start - timedelta(days=1)}. Nothing to do.")
        print(f"  Use --start to re-crawl from a specific date.")
        return

    total_days = (crawl_end - crawl_start).days + 1
    print(f"Discovering repos with >{min_stars} stars")
    print(f"  Date range: {crawl_start} to {crawl_end} ({total_days} days)")
    print()

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    else:
        print("WARNING: No GitHub token. Rate limit is 10 searches/min (very slow).", file=sys.stderr)
        print("  Set GITHUB_TOKEN or use --token for 30 searches/min.\n", file=sys.stderr)

    total_added = 0
    current = crawl_start

    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as session:
        while current <= crawl_end:
            # Process one week at a time (or remaining days)
            chunk_end = min(current + timedelta(days=6), crawl_end)

            progress_pct = ((current - crawl_start).days / max(total_days, 1)) * 100
            print(
                f"  [{progress_pct:5.1f}%] {current} .. {chunk_end}",
                end="",
                flush=True,
            )

            await asyncio.sleep(SEARCH_DELAY)
            added = await _crawl_date_range(
                session, min_stars, current, chunk_end, db_path
            )
            total_added += added

            print(f"  +{added} repos")

            # Save progress
            set_discover_state(
                "last_crawled_date", chunk_end.isoformat(), db_path
            )

            current = chunk_end + timedelta(days=1)

    print(f"\nDiscovery complete: {total_added} new repos added.")
    print(f"  Crawled up to: {crawl_end}")
