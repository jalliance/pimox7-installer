from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

from .base import BaseSource, FoundResult

if TYPE_CHECKING:
    from ..parser import RepoInfo


class GoogleCacheSource(BaseSource):
    name = "google"

    async def search(
        self, info: RepoInfo, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        # Use the original URL for Google Cache lookups
        origin_host_path = re.sub(r"^https?://", "", info.origin_url)

        cache_url = (
            f"https://webcache.googleusercontent.com/search"
            f"?q=cache:{origin_host_path}"
        )
        search_url = (
            f"https://www.google.com/search"
            f"?q=cache:{origin_host_path}"
        )

        # Try to actually fetch the cache (often blocked, but worth a shot)
        try:
            resp = await session.get(cache_url, timeout=10)
            if resp.status_code == 200 and info.repo.lower() in resp.text.lower():
                return [
                    FoundResult(
                        source_name="Google Cache",
                        url=cache_url,
                        description="Cached copy of repo page found in Google Cache",
                        confidence="low",
                    )
                ]
        except Exception:
            pass

        # Return the URL as a manual suggestion
        return [
            FoundResult(
                source_name="Google Cache (manual)",
                url=search_url,
                description="Try this Google search URL manually in your browser to check for cached pages",
                confidence="low",
            )
        ]
