import httpx

from .base import BaseSource, FoundResult
from ..rate_limit import safe_get_or_none


class GitHubForksSource(BaseSource):
    name = "forks"

    async def search(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        results = []

        # Strategy 1: Try the forks endpoint directly (works if repo still exists
        # or if GitHub redirects to the new upstream after deletion)
        forks = await self._try_forks_endpoint(owner, repo, session)
        results.extend(forks)

        # Strategy 2: Search API for repos with the same name that are forks
        if not results:
            search_results = await self._try_search_api(owner, repo, session)
            results.extend(search_results)

        return results

    async def _try_forks_endpoint(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        url = f"https://api.github.com/repos/{owner}/{repo}/forks"
        resp = await safe_get_or_none(
            session, url, params={"sort": "newest", "per_page": "30"}
        )
        if not resp:
            return []

        results = []
        for fork in resp.json():
            full_name = fork.get("full_name", "")
            html_url = fork.get("html_url", "")
            clone_url = fork.get("clone_url", "")
            updated = fork.get("updated_at", "")
            stars = fork.get("stargazers_count", 0)

            desc = f"Fork by {fork.get('owner', {}).get('login', '?')}"
            if stars:
                desc += f" ({stars} stars)"

            results.append(
                FoundResult(
                    source_name=f"GitHub Fork: {full_name}",
                    url=html_url,
                    description=desc,
                    clone_url=clone_url,
                    confidence="high",
                    timestamp=updated,
                )
            )

        return results

    async def _try_search_api(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        url = "https://api.github.com/search/repositories"
        params = {
            "q": f"{repo} fork:only",
            "sort": "updated",
            "per_page": "30",
        }
        resp = await safe_get_or_none(session, url, params=params)
        if not resp:
            return []

        data = resp.json()
        results = []
        for item in data.get("items", []):
            # Check if this fork's parent matches our target repo
            parent = item.get("parent", {}) or {}
            source = item.get("source", {}) or {}
            parent_name = parent.get("full_name", "").lower()
            source_name = source.get("full_name", "").lower()
            target = f"{owner}/{repo}".lower()

            # Match on parent, source, or just same repo name
            is_match = (
                parent_name == target
                or source_name == target
                or item.get("name", "").lower() == repo.lower()
            )
            if not is_match:
                continue

            full_name = item.get("full_name", "")
            html_url = item.get("html_url", "")
            clone_url = item.get("clone_url", "")
            updated = item.get("updated_at", "")
            stars = item.get("stargazers_count", 0)

            desc = f"Fork found via GitHub search"
            if stars:
                desc += f" ({stars} stars)"

            results.append(
                FoundResult(
                    source_name=f"GitHub Fork: {full_name}",
                    url=html_url,
                    description=desc,
                    clone_url=clone_url,
                    confidence="high",
                    timestamp=updated,
                )
            )

            if len(results) >= 10:
                break

        return results
