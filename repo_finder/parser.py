import re
from dataclasses import dataclass
from typing import Optional


# Known git hosting platforms: (domain_pattern, platform_name, owner_extractor)
KNOWN_HOSTS = [
    (r"(?:www\.)?github\.com", "github"),
    (r"(?:www\.)?gitlab\.com", "gitlab"),
    (r"(?:www\.)?codeberg\.org", "codeberg"),
    (r"(?:www\.)?bitbucket\.org", "bitbucket"),
    (r"git\.sr\.ht", "sourcehut"),
    (r"(?:www\.)?gitea\.com", "gitea"),
    (r"(?:www\.)?notabug\.org", "notabug"),
]


@dataclass
class RepoInfo:
    owner: str
    repo: str
    platform: str  # "github", "gitlab", "bitbucket", etc. or "unknown"
    origin_url: str  # full original URL (e.g. "https://gitlab.com/owner/repo")


def parse_repo_input(raw: str) -> RepoInfo:
    """Parse a git repo identifier into a RepoInfo.

    Accepts:
      - "owner/repo" (assumes GitHub)
      - "https://github.com/owner/repo"
      - "https://gitlab.com/owner/repo"
      - "https://bitbucket.org/owner/repo"
      - "https://codeberg.org/owner/repo"
      - "https://git.sr.ht/~owner/repo"
      - Any of the above with a trailing ".git"
      - Any of the above with trailing slashes or path segments
    """
    text = raw.strip().rstrip("/")

    # Strip .git suffix
    if text.endswith(".git"):
        text = text[:-4]

    # Strip scheme for matching
    without_scheme = re.sub(r"^https?://", "", text)

    # Try to match against known hosts
    for host_pattern, platform in KNOWN_HOSTS:
        match = re.match(rf"^{host_pattern}/(.+)$", without_scheme)
        if match:
            path = match.group(1)
            parts = path.split("/")

            # SourceHut uses ~owner/repo
            if platform == "sourcehut":
                if len(parts) < 2:
                    raise ValueError(
                        f"Invalid repo identifier: {raw!r}. "
                        f"Expected '~owner/repo' path for SourceHut."
                    )
                owner = parts[0].lstrip("~")
                repo = parts[1]
            else:
                if len(parts) < 2:
                    raise ValueError(
                        f"Invalid repo identifier: {raw!r}. "
                        f"Expected 'owner/repo' path."
                    )
                owner, repo = parts[0], parts[1]

            if not owner or not repo:
                raise ValueError(
                    f"Invalid repo identifier: {raw!r}. "
                    f"Owner and repo name must be non-empty."
                )

            # Reconstruct canonical origin URL
            host_match = re.match(rf"^({host_pattern})", without_scheme)
            host = host_match.group(1)
            if platform == "sourcehut":
                origin_url = f"https://{host}/~{owner}/{repo}"
            else:
                origin_url = f"https://{host}/{owner}/{repo}"

            return RepoInfo(
                owner=owner, repo=repo, platform=platform, origin_url=origin_url
            )

    # No known host matched — check if it's a bare "owner/repo" (assume GitHub)
    parts = without_scheme.split("/")
    if len(parts) == 2 and "." not in parts[0]:
        owner, repo = parts[0], parts[1]
        if owner and repo:
            return RepoInfo(
                owner=owner,
                repo=repo,
                platform="github",
                origin_url=f"https://github.com/{owner}/{repo}",
            )

    # Could be an unknown host URL — try to extract owner/repo from path
    match = re.match(r"^([^/]+\.[^/]+)/(.+)$", without_scheme)
    if match:
        host = match.group(1)
        path = match.group(2)
        parts = path.split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            if owner and repo:
                return RepoInfo(
                    owner=owner,
                    repo=repo,
                    platform="unknown",
                    origin_url=f"https://{host}/{owner}/{repo}",
                )

    raise ValueError(
        f"Invalid repo identifier: {raw!r}. "
        f"Expected 'owner/repo' or a git hosting URL."
    )
