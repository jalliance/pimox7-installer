from flask import Flask, render_template, request, jsonify, redirect, url_for
import asyncio
import math
import os

from ..parser import parse_repo_input
from ..core import run_search
from ..scanner.db import (
    init_db, add_repo, list_repos, count_repos, get_stats, get_discover_state,
)

app = Flask(__name__)
PER_PAGE = 50


def _ensure_db():
    init_db()


def _run_search(repo_input: str, token: str | None = None) -> dict:
    """Run the async search synchronously and return structured results."""
    try:
        info = parse_repo_input(repo_input)
    except ValueError as e:
        return {"error": str(e), "results": [], "info": None}

    results = asyncio.run(run_search(info, token=token, timeout=20))

    result_dicts = [r.to_dict() for r in results]
    source_categories = {r.source_name.split(":")[0].strip() for r in results}

    return {
        "error": None,
        "info": {
            "owner": info.owner,
            "repo": info.repo,
            "platform": info.platform,
            "origin_url": info.origin_url,
        },
        "results": result_dicts,
        "source_count": len(source_categories),
    }


def _paginate(status=None, page=1, order_by="stars DESC"):
    total = count_repos(status=status)
    total_pages = max(1, math.ceil(total / PER_PAGE))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PER_PAGE
    repos = list_repos(status=status, limit=PER_PAGE, offset=offset, order_by=order_by)
    return repos, page, total_pages, total


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return render_template("index.html")

    token = os.environ.get("GITHUB_TOKEN")
    data = _run_search(query, token=token)
    return render_template("index.html", query=query, data=data)


@app.route("/removed")
def removed():
    _ensure_db()
    page = request.args.get("page", 1, type=int)
    repos, page, total_pages, total = _paginate(status="removed", page=page, order_by="removed_at DESC")
    stats = get_stats()
    return render_template(
        "removed.html", repos=repos, stats=stats,
        page=page, total_pages=total_pages, total=total,
    )


@app.route("/watched")
def watched():
    _ensure_db()
    page = request.args.get("page", 1, type=int)
    filter_status = request.args.get("status")
    status = filter_status if filter_status in ("alive", "removed") else None
    repos, page, total_pages, total = _paginate(status=status, page=page)
    stats = get_stats()
    last_crawled = get_discover_state("last_crawled_date")
    return render_template(
        "watched.html", repos=repos, stats=stats,
        current_filter=filter_status,
        page=page, total_pages=total_pages, total=total,
        last_crawled=last_crawled,
    )


@app.route("/watch", methods=["POST"])
def watch():
    url = request.form.get("url", "").strip()
    if url:
        try:
            info = parse_repo_input(url)
            _ensure_db()
            add_repo(info.owner, info.repo, info.platform, info.origin_url)
        except ValueError:
            pass
    return redirect(request.referrer or url_for("watched"))


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    token = os.environ.get("GITHUB_TOKEN")
    data = _run_search(query, token=token)
    return jsonify(data)


@app.route("/api/removed")
def api_removed():
    _ensure_db()
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", PER_PAGE, type=int)
    offset = (page - 1) * limit
    repos = list_repos(status="removed", limit=limit, offset=offset, order_by="removed_at DESC")
    total = count_repos(status="removed")
    return jsonify({"repos": repos, "total": total, "page": page})


@app.route("/api/watched")
def api_watched():
    _ensure_db()
    repos = list_repos(limit=100)
    stats = get_stats()
    return jsonify({"repos": repos, "stats": stats})


def main():
    port = int(os.environ.get("PORT", 5000))
    _ensure_db()
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", False))
