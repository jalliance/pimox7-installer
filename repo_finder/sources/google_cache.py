import httpx

from .base import BaseSource, FoundResult


class GoogleCacheSource(BaseSource):
    name = "google"

    async def search(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        # Google Cache doesn't have a reliable API for automated access.
        # We generate the URLs for the user to try manually.
        cache_url = (
            f"https://webcache.googleusercontent.com/search"
            f"?q=cache:github.com/{owner}/{repo}"
        )
        search_url = (
            f"https://www.google.com/search"
            f"?q=cache:github.com/{owner}/{repo}"
        )

        # Try to actually fetch the cache (often blocked, but worth a shot)
        try:
            resp = await session.get(cache_url, timeout=10)
            if resp.status_code == 200 and "github.com" in resp.text.lower():
                return [
                    FoundResult(
                        source_name="Google Cache",
                        url=cache_url,
                        description="Cached copy of GitHub repo page found in Google Cache",
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
