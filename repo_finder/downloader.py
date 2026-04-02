import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

import httpx

from .sources.base import FoundResult


CLONE_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def _pick_best(results: list[FoundResult]) -> FoundResult | None:
    """Pick the best result for downloading. Prefers cloneable repos."""
    cloneable = [r for r in results if r.clone_url]
    if cloneable:
        cloneable.sort(key=lambda r: CLONE_PRIORITY.get(r.confidence, 9))
        return cloneable[0]
    # Fall back to any high/medium result with a URL
    downloadable = [r for r in results if r.confidence != "low"]
    if downloadable:
        return downloadable[0]
    return results[0] if results else None


def _has_git() -> bool:
    return shutil.which("git") is not None


def _git_clone(clone_url: str, output_dir: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "clone", clone_url, output_dir],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  Cloned to {output_dir}")
            return True
        else:
            print(f"  git clone failed: {result.stderr.strip()}", file=sys.stderr)
            return False
    except OSError as e:
        print(f"  git clone error: {e}", file=sys.stderr)
        return False


def _download_archive(url: str, output_dir: str) -> bool:
    """Download a tarball/zip from a URL and extract it."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            resp = client.get(url)
            resp.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".archive") as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        try:
            if tarfile.is_tarfile(tmp_path):
                with tarfile.open(tmp_path) as tf:
                    tf.extractall(output_dir, filter="data")
                print(f"  Extracted tarball to {output_dir}")
                return True
            elif zipfile.is_zipfile(tmp_path):
                with zipfile.ZipFile(tmp_path) as zf:
                    zf.extractall(output_dir)
                print(f"  Extracted zip to {output_dir}")
                return True
            else:
                # Just save the raw file
                dest = os.path.join(output_dir, "downloaded_content")
                shutil.move(tmp_path, dest)
                print(f"  Saved to {dest}")
                return True
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        print(f"  Download failed: {e}", file=sys.stderr)
        return False


def offer_download(results: list[FoundResult], output_dir: str) -> None:
    """Offer to download/clone the best available copy."""
    best = _pick_best(results)
    if not best:
        print("No results available for download.")
        return

    print()
    print(f"Best available: {best.source_name} ({best.confidence} confidence)")
    if best.clone_url:
        print(f"  Clone URL: {best.clone_url}")
    else:
        print(f"  URL: {best.url}")

    try:
        answer = input("\nDownload this? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nSkipped.")
        return

    if answer and answer not in ("y", "yes"):
        print("Skipped.")
        return

    print(f"\nDownloading to {output_dir}...")

    if best.clone_url and _has_git():
        if _git_clone(best.clone_url, output_dir):
            return

    # Fall back to archive download
    download_url = best.clone_url or best.url
    if download_url:
        _download_archive(download_url, output_dir)
    else:
        print("No downloadable URL available. Visit the URL manually:")
        print(f"  {best.url}")
