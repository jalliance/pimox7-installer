import httpx

from .base import BaseSource, FoundResult
from ..rate_limit import safe_get_or_none


MIRRORS = [
    {
        "name": "GitLab",
        "api_url": "https://gitlab.com/api/v4/projects/{owner}%2F{repo}",
        "html_url": "https://gitlab.com/{owner}/{repo}",
        "clone_tmpl": "https://gitlab.com/{owner}/{repo}.git",
        "json_fields": {"description": "description", "updated": "last_activity_at"},
    },
    {
        "name": "Codeberg",
        "api_url": "https://codeberg.org/api/v1/repos/{owner}/{repo}",
        "html_url": "https://codeberg.org/{owner}/{repo}",
        "clone_tmpl": "https://codeberg.org/{owner}/{repo}.git",
        "json_fields": {"description": "description", "updated": "updated_at"},
    },
    {
        "name": "Bitbucket",
        "api_url": "https://api.bitbucket.org/2.0/repositories/{owner}/{repo}",
        "html_url": "https://bitbucket.org/{owner}/{repo}",
        "clone_tmpl": "https://bitbucket.org/{owner}/{repo}.git",
        "json_fields": {"description": "description", "updated": "updated_on"},
    },
]


class GitMirrorsSource(BaseSource):
    name = "mirrors"

    async def search(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        results = []
        for mirror in MIRRORS:
            result = await self._check_mirror(owner, repo, session, mirror)
            if result:
                results.append(result)

        # Also check SourceHut (HTML check, no JSON API for anon)
        srht = await self._check_sourcehut(owner, repo, session)
        if srht:
            results.append(srht)

        return results

    async def _check_mirror(
        self,
        owner: str,
        repo: str,
        session: httpx.AsyncClient,
        mirror: dict,
    ) -> FoundResult | None:
        api_url = mirror["api_url"].format(owner=owner, repo=repo)
        resp = await safe_get_or_none(session, api_url)
        if not resp:
            return None

        data = resp.json()
        fields = mirror["json_fields"]
        description = data.get(fields.get("description", ""), "") or ""
        updated = data.get(fields.get("updated", ""), "")

        html_url = mirror["html_url"].format(owner=owner, repo=repo)
        clone_url = mirror["clone_tmpl"].format(owner=owner, repo=repo)

        return FoundResult(
            source_name=f"{mirror['name']} Mirror",
            url=html_url,
            description=f"Mirror on {mirror['name']}"
            + (f": {description[:80]}" if description else ""),
            clone_url=clone_url,
            confidence="high",
            timestamp=updated or None,
        )

    async def _check_sourcehut(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> FoundResult | None:
        url = f"https://git.sr.ht/~{owner}/{repo}"
        resp = await safe_get_or_none(session, url)
        if not resp:
            return None
        if resp.status_code == 200:
            return FoundResult(
                source_name="SourceHut Mirror",
                url=url,
                description=f"Mirror on SourceHut (git.sr.ht)",
                clone_url=f"https://git.sr.ht/~{owner}/{repo}",
                confidence="high",
            )
        return None
