from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

from .base import BaseSource, FoundResult
from ..rate_limit import safe_get_or_none

if TYPE_CHECKING:
    from ..parser import RepoInfo


class PackageRegistriesSource(BaseSource):
    name = "packages"

    async def search(
        self, info: RepoInfo, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        results = []
        # Match against the origin URL (works for any platform)
        origin_pattern = re.sub(r"^https?://", "", info.origin_url).lower()

        # Check npm
        npm_result = await self._check_npm(info.repo, origin_pattern, session)
        if npm_result:
            results.append(npm_result)

        # Check PyPI
        pypi_result = await self._check_pypi(info.repo, origin_pattern, session)
        if pypi_result:
            results.append(pypi_result)

        # Check crates.io
        crates_result = await self._check_crates(info.repo, origin_pattern, session)
        if crates_result:
            results.append(crates_result)

        # Check RubyGems
        gems_result = await self._check_rubygems(info.repo, origin_pattern, session)
        if gems_result:
            results.append(gems_result)

        return results

    async def _check_npm(
        self, repo: str, target: str, session: httpx.AsyncClient
    ) -> FoundResult | None:
        resp = await safe_get_or_none(session, f"https://registry.npmjs.org/{repo}")
        if not resp:
            return None

        data = resp.json()
        # Check if repository URL matches
        repo_url = ""
        repo_info = data.get("repository")
        if isinstance(repo_info, dict):
            repo_url = repo_info.get("url", "")
        elif isinstance(repo_info, str):
            repo_url = repo_info

        if target not in repo_url.lower():
            return None

        version = data.get("dist-tags", {}).get("latest", "?")
        npm_url = f"https://www.npmjs.com/package/{repo}"

        # Get tarball URL
        tarball = None
        versions = data.get("versions", {})
        latest_data = versions.get(version, {})
        dist = latest_data.get("dist", {})
        tarball = dist.get("tarball")

        return FoundResult(
            source_name="npm Registry",
            url=npm_url,
            description=f"npm package '{repo}' v{version} linked to this repo",
            clone_url=tarball,
            confidence="medium",
        )

    async def _check_pypi(
        self, repo: str, target: str, session: httpx.AsyncClient
    ) -> FoundResult | None:
        resp = await safe_get_or_none(session, f"https://pypi.org/pypi/{repo}/json")
        if not resp:
            return None

        data = resp.json()
        info = data.get("info", {})

        # Check homepage and project URLs for match
        all_urls = []
        if info.get("home_page"):
            all_urls.append(info["home_page"])
        for url in (info.get("project_urls") or {}).values():
            all_urls.append(url)

        if not any(target in u.lower() for u in all_urls):
            return None

        version = info.get("version", "?")
        pypi_url = f"https://pypi.org/project/{repo}/"

        # Find source tarball
        tarball = None
        for file_info in data.get("urls", []):
            if file_info.get("packagetype") == "sdist":
                tarball = file_info.get("url")
                break

        return FoundResult(
            source_name="PyPI Registry",
            url=pypi_url,
            description=f"PyPI package '{repo}' v{version} linked to this repo",
            clone_url=tarball,
            confidence="medium",
        )

    async def _check_crates(
        self, repo: str, target: str, session: httpx.AsyncClient
    ) -> FoundResult | None:
        resp = await safe_get_or_none(
            session, f"https://crates.io/api/v1/crates/{repo}"
        )
        if not resp:
            return None

        data = resp.json()
        crate = data.get("crate", {})
        crate_repo = crate.get("repository", "") or ""

        if target not in crate_repo.lower():
            return None

        version = crate.get("newest_version", "?")
        crates_url = f"https://crates.io/crates/{repo}"

        # Download URL
        dl_path = None
        versions = data.get("versions", [])
        if versions:
            dl_path = f"https://crates.io{versions[0].get('dl_path', '')}"

        return FoundResult(
            source_name="crates.io Registry",
            url=crates_url,
            description=f"Rust crate '{repo}' v{version} linked to this repo",
            clone_url=dl_path,
            confidence="medium",
        )

    async def _check_rubygems(
        self, repo: str, target: str, session: httpx.AsyncClient
    ) -> FoundResult | None:
        resp = await safe_get_or_none(
            session, f"https://rubygems.org/api/v1/gems/{repo}.json"
        )
        if not resp:
            return None

        data = resp.json()
        source_uri = (data.get("source_code_uri") or "").lower()
        homepage = (data.get("homepage_uri") or "").lower()

        if target not in source_uri and target not in homepage:
            return None

        version = data.get("version", "?")
        gems_url = f"https://rubygems.org/gems/{repo}"
        gem_uri = data.get("gem_uri")

        return FoundResult(
            source_name="RubyGems Registry",
            url=gems_url,
            description=f"Ruby gem '{repo}' v{version} linked to this repo",
            clone_url=gem_uri,
            confidence="medium",
        )
