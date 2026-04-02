import httpx

from .base import BaseSource, FoundResult
from ..rate_limit import safe_get_or_none


SWH_API = "https://archive.softwareheritage.org/api/1"


class SoftwareHeritageSource(BaseSource):
    name = "swh"

    async def search(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        origin_url = f"https://github.com/{owner}/{repo}"

        # Step 1: Check if the origin exists in Software Heritage
        resp = await safe_get_or_none(
            session, f"{SWH_API}/origin/{origin_url}/get/"
        )
        if not resp:
            return []

        results = []

        # The origin exists — add browse link
        browse_url = (
            f"https://archive.softwareheritage.org/browse/origin/directory/"
            f"?origin_url={origin_url}"
        )

        # Step 2: Get visit info for timestamps and snapshot IDs
        visits_resp = await safe_get_or_none(
            session, f"{SWH_API}/origin/{origin_url}/visits/", params={"per_page": "5"}
        )

        latest_date = None
        snapshot_swhid = None
        if visits_resp:
            visits = visits_resp.json()
            if isinstance(visits, list) and visits:
                # Find latest successful visit
                for visit in visits:
                    if visit.get("status") == "full" and visit.get("snapshot"):
                        latest_date = visit.get("date", "")[:10]
                        snapshot_swhid = visit.get("snapshot")
                        break
                if not latest_date and visits:
                    latest_date = visits[0].get("date", "")[:10]

        results.append(
            FoundResult(
                source_name="Software Heritage Archive",
                url=browse_url,
                description="Full source code preserved in Software Heritage",
                confidence="high",
                timestamp=latest_date,
            )
        )

        # Step 3: If we have a snapshot, try to provide a vault download link
        if snapshot_swhid:
            vault_url = (
                f"https://archive.softwareheritage.org/api/1/vault/"
                f"git-bare/swh:1:snp:{snapshot_swhid}/"
            )
            results.append(
                FoundResult(
                    source_name="Software Heritage Vault",
                    url=vault_url,
                    description=(
                        "Downloadable git-bare archive (may need to be cooked first — "
                        "POST to this URL to trigger, then GET to poll/download)"
                    ),
                    confidence="high",
                    timestamp=latest_date,
                )
            )

        return results
