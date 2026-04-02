import json
import sys

from .sources.base import FoundResult

# ANSI colors
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"

CONFIDENCE_COLORS = {
    "high": GREEN,
    "medium": YELLOW,
    "low": RED,
}


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def print_report(results: list[FoundResult], owner: str, repo: str) -> None:
    color = _supports_color()

    def c(code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if color else text

    print()
    print(c(BOLD, f"=== Archived copies of {owner}/{repo} ==="))
    print()

    if not results:
        print(c(RED, "No archived copies found."))
        print()
        print("Suggestions:")
        print("  - Try searching manually on https://web.archive.org/")
        print("  - Try https://archive.softwareheritage.org/")
        print("  - Search GitHub for forks: https://github.com/search?q=" + repo)
        return

    grouped: dict[str, list[FoundResult]] = {"high": [], "medium": [], "low": []}
    for r in results:
        grouped.setdefault(r.confidence, []).append(r)

    for level in ("high", "medium", "low"):
        items = grouped.get(level, [])
        if not items:
            continue

        conf_color = CONFIDENCE_COLORS.get(level, "")
        print(c(conf_color + BOLD, f"  [{level.upper()}] confidence"))
        print()

        for r in items:
            print(f"    {c(BOLD, r.source_name)}")
            print(f"      {r.description}")
            print(f"      URL: {c(CYAN, r.url)}")
            if r.clone_url:
                print(f"      Clone: git clone {c(CYAN, r.clone_url)}")
            if r.timestamp:
                print(f"      Snapshot: {c(DIM, r.timestamp)}")
            print()

    total = len(results)
    # Normalize source names for counting (e.g. "GitHub Fork: user/repo" -> "GitHub Fork")
    source_categories = {r.source_name.split(":")[0].strip() for r in results}
    print(c(DIM, f"Found {total} result(s) across {len(source_categories)} source(s)."))
    print()


def print_json(results: list[FoundResult]) -> None:
    print(json.dumps([r.to_dict() for r in results], indent=2))
