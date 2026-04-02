import asyncio
import sys

import httpx

from .sources.base import FoundResult


CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


async def run_search(
    owner: str,
    repo: str,
    token: str | None = None,
    source_filter: list[str] | None = None,
    timeout: int = 30,
) -> list[FoundResult]:
    from .sources import ALL_SOURCES, SOURCE_NAMES

    if source_filter:
        sources = []
        for name in source_filter:
            if name in SOURCE_NAMES:
                sources.append(SOURCE_NAMES[name])
            else:
                print(
                    f"[!] Unknown source: {name!r}. "
                    f"Available: {', '.join(SOURCE_NAMES)}",
                    file=sys.stderr,
                )
        if not sources:
            return []
    else:
        sources = ALL_SOURCES

    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=headers
    ) as session:
        tasks = [source.search(owner, repo, session) for source in sources]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for source, result in zip(sources, results_nested):
        if isinstance(result, BaseException):
            print(f"[!] {source.name} failed: {result}", file=sys.stderr)
        else:
            results.extend(result)

    results.sort(key=lambda r: CONFIDENCE_ORDER.get(r.confidence, 9))
    return results
