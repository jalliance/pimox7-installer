import httpx

from .base import BaseSource, FoundResult
from ..rate_limit import safe_get_or_none


class WaybackSource(BaseSource):
    name = "wayback"

    async def search(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        results = []

        # Search for archived GitHub repo pages
        repo_snapshots = await self._search_cdx(
            session, f"github.com/{owner}/{repo}", limit=20
        )
        if repo_snapshots:
            latest = repo_snapshots[0]
            results.append(
                FoundResult(
                    source_name="Wayback Machine",
                    url=f"https://web.archive.org/web/{latest['timestamp']}/https://github.com/{owner}/{repo}",
                    description=f"Archived GitHub page ({len(repo_snapshots)} snapshots found)",
                    confidence="medium",
                    timestamp=self._format_timestamp(latest["timestamp"]),
                )
            )

        # Search for archived raw file content
        raw_snapshots = await self._search_cdx(
            session, f"raw.githubusercontent.com/{owner}/{repo}/*", limit=50
        )
        if raw_snapshots:
            # Deduplicate by path
            unique_paths = {}
            for snap in raw_snapshots:
                path = snap["original"]
                if path not in unique_paths:
                    unique_paths[path] = snap

            results.append(
                FoundResult(
                    source_name="Wayback Machine (raw files)",
                    url=f"https://web.archive.org/web/*/raw.githubusercontent.com/{owner}/{repo}/*",
                    description=f"{len(unique_paths)} unique raw file(s) archived",
                    confidence="medium",
                    timestamp=self._format_timestamp(raw_snapshots[0]["timestamp"]),
                )
            )

        # Check for archived tarball/zip downloads
        for pattern in [
            f"github.com/{owner}/{repo}/archive/*",
            f"codeload.github.com/{owner}/{repo}/*",
        ]:
            archive_snaps = await self._search_cdx(session, pattern, limit=5)
            if archive_snaps:
                snap = archive_snaps[0]
                wb_url = f"https://web.archive.org/web/{snap['timestamp']}/{snap['original']}"
                results.append(
                    FoundResult(
                        source_name="Wayback Machine (archive download)",
                        url=wb_url,
                        description=f"Archived repo download: {snap['original'].split('/')[-1]}",
                        confidence="medium",
                        timestamp=self._format_timestamp(snap["timestamp"]),
                    )
                )
                break

        return results

    async def _search_cdx(
        self, session: httpx.AsyncClient, url_pattern: str, limit: int = 20
    ) -> list[dict]:
        """Query the Wayback CDX API for snapshots of a URL pattern."""
        cdx_url = "https://web.archive.org/cdx/search/cdx"
        params = {
            "url": url_pattern,
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype",
            "filter": "statuscode:200",
            "collapse": "urlkey",
            "limit": str(limit),
            "sort": "reverse",  # newest first
        }

        # Use matchType=prefix for wildcard patterns
        if url_pattern.endswith("*"):
            params["url"] = url_pattern.rstrip("*")
            params["matchType"] = "prefix"

        resp = await safe_get_or_none(session, cdx_url, params=params)
        if not resp:
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        if not data or len(data) < 2:
            return []

        # First row is header
        headers = data[0]
        rows = data[1:]

        return [dict(zip(headers, row)) for row in rows]

    @staticmethod
    def _format_timestamp(ts: str) -> str:
        """Format a Wayback timestamp (yyyyMMddHHmmss) to readable date."""
        if len(ts) >= 8:
            return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        return ts
