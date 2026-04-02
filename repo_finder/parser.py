import re


def parse_repo_input(raw: str) -> tuple[str, str]:
    """Parse a GitHub repo identifier into (owner, repo).

    Accepts:
      - "owner/repo"
      - "https://github.com/owner/repo"
      - "http://github.com/owner/repo"
      - "github.com/owner/repo"
      - Any of the above with a trailing ".git"
      - Any of the above with trailing slashes or path segments
    """
    text = raw.strip().rstrip("/")

    # Strip .git suffix
    if text.endswith(".git"):
        text = text[:-4]

    # Strip scheme
    text = re.sub(r"^https?://", "", text)

    # Strip github.com prefix
    text = re.sub(r"^(www\.)?github\.com/", "", text)

    # Strip any trailing path segments beyond owner/repo (e.g. /tree/main)
    parts = text.split("/")
    if len(parts) < 2:
        raise ValueError(
            f"Invalid repo identifier: {raw!r}. Expected 'owner/repo' or a GitHub URL."
        )

    owner, repo = parts[0], parts[1]
    if not owner or not repo:
        raise ValueError(
            f"Invalid repo identifier: {raw!r}. Owner and repo name must be non-empty."
        )

    return owner, repo
