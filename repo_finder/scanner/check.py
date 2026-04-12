"""Scanner that checks if watched repos are still alive."""

import asyncio
import sys

import httpx

from .db import init_db, list_repos, update_repo_status, get_stats


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

    # Fallback: HEAD/GET the origin URL directly (HTML page)
    try:
        resp = await session.head(repo["origin_url"], timeout=15)
        status = resp.status_code
        if status in GONE_STATUSES:
            return False, status
        return True, status
    except (httpx.TimeoutException, httpx.ConnectError):
        # Network error — don't mark as removed, just skip
        return True, None


async def run_scan(token: str | None = None, db_path: str | None = None):
    """Scan all watched repos and update their status."""
    init_db(db_path)
    repos = list_repos(db_path=db_path)

    if not repos:
        print("No repos to scan. Add some with: python -m repo_finder.scanner add <url>")
        return

    print(f"Scanning {len(repos)} watched repos...")

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"

    newly_removed = []

    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as session:
        # Process in batches to respect rate limits
        batch_size = 10
        for i in range(0, len(repos), batch_size):
            batch = repos[i : i + batch_size]
            tasks = [check_repo(session, r) for r in batch]
            results = await asyncio.gather(*tasks)

            for repo, (alive, http_status) in zip(batch, results):
                was_alive = repo["status"] == "alive"
                update_repo_status(
                    repo["id"], alive, http_status, db_path=db_path
                )
                if was_alive and not alive:
                    newly_removed.append(repo)
                    print(f"  REMOVED: {repo['origin_url']} (HTTP {http_status})")
                elif alive:
                    print(f"  OK: {repo['origin_url']}")
                else:
                    print(f"  still gone: {repo['origin_url']}")

            # Small delay between batches to be polite
            if i + batch_size < len(repos):
                await asyncio.sleep(1)

    stats = get_stats(db_path)
    print(f"\nScan complete: {stats['alive']} alive, {stats['removed']} removed, {stats['total']} total")

    if newly_removed:
        print(f"\n{len(newly_removed)} repo(s) newly removed:")
        for r in newly_removed:
            print(f"  - {r['origin_url']}")

    return newly_removed
