"""Scanner that checks if watched repos are still alive."""

import asyncio
import sys

import httpx

from .db import init_db, get_unchecked_repos, update_repo_status, get_stats, count_repos


# HTTP status codes that mean "repo is gone"
GONE_STATUSES = {404, 410, 451}

# Platform-specific check URLs (API endpoints)
PLATFORM_API_URLS = {
    "github": "https://api.github.com/repos/{owner}/{repo}",
    "gitlab": "https://gitlab.com/api/v4/projects/{owner}%2F{repo}",
    "codeberg": "https://codeberg.org/api/v1/repos/{owner}/{repo}",
    "bitbucket": "https://api.bitbucket.org/2.0/repositories/{owner}/{repo}",
}


async def check_repo(
    session: httpx.AsyncClient, repo: dict
) -> tuple[bool, int | None]:
    """Check if a single repo is still alive. Returns (alive, http_status)."""
    platform = repo["platform"]
    owner = repo["owner"]
    repo_name = repo["repo"]

    # Try API endpoint first
    if platform in PLATFORM_API_URLS:
        url = PLATFORM_API_URLS[platform].format(owner=owner, repo=repo_name)
        try:
            resp = await session.get(url, timeout=15)
            status = resp.status_code
            if status in GONE_STATUSES:
                return False, status
            if status == 200:
                return True, status
            # 403 could be rate limiting — fall through to HTML check
        except (httpx.TimeoutException, httpx.ConnectError):
            pass

    # Fallback: HEAD the origin URL directly (HTML page)
    try:
        resp = await session.head(repo["origin_url"], timeout=15)
        status = resp.status_code
        if status in GONE_STATUSES:
            return False, status
        return True, status
    except (httpx.TimeoutException, httpx.ConnectError):
        # Network error — don't mark as removed, just skip
        return True, None


async def run_scan(
    token: str | None = None,
    batch_limit: int = 1000,
    quiet: bool = False,
    db_path: str | None = None,
):
    """Scan watched repos and update their status.

    Processes repos in order of staleness (least recently checked first).
    batch_limit controls how many repos to check per invocation.
    """
    init_db(db_path)
    repos = get_unchecked_repos(limit=batch_limit, db_path=db_path)

    if not repos:
        total = count_repos(db_path=db_path)
        if total == 0:
            print("No repos to scan. Run 'discover' first or add repos manually.")
        else:
            print(f"All {total} repos recently checked.")
        return

    total_count = count_repos(db_path=db_path)
    if not quiet:
        print(f"Scanning {len(repos)} repos (of {total_count} total)...")

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"

    newly_removed = []
    checked = 0

    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as session:
        batch_size = 20
        for i in range(0, len(repos), batch_size):
            batch = repos[i : i + batch_size]
            tasks = [check_repo(session, r) for r in batch]
            results = await asyncio.gather(*tasks)

            for repo, (alive, http_status) in zip(batch, results):
                was_alive = repo["status"] == "alive"
                update_repo_status(
                    repo["id"], alive, http_status, db_path=db_path
                )
                checked += 1

                if was_alive and not alive:
                    newly_removed.append(repo)
                    print(f"  REMOVED: {repo['origin_url']} (HTTP {http_status})")
                elif not quiet:
                    if alive:
                        # Only print every Nth to avoid flood
                        if checked % 100 == 0 or checked == len(repos):
                            print(f"  [{checked}/{len(repos)}] checked...")
                    else:
                        print(f"  still gone: {repo['origin_url']}")

            # Delay between batches to respect rate limits
            if i + batch_size < len(repos):
                await asyncio.sleep(0.5)

    stats = get_stats(db_path)
    print(
        f"\nScan complete: checked {checked}, "
        f"{stats['alive']} alive, {stats['removed']} removed, {stats['total']} total"
    )

    if newly_removed:
        print(f"\n{len(newly_removed)} repo(s) newly removed:")
        for r in newly_removed:
            stars = r.get("stars", 0)
            print(f"  - {r['origin_url']} ({stars} stars)")

    return newly_removed
