from flask import Flask, render_template, request, jsonify, redirect, url_for
import asyncio
import os

from ..parser import parse_repo_input
from ..core import run_search
from ..scanner.db import init_db, add_repo, list_repos, get_stats

app = Flask(__name__)


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
    repos = list_repos(status="removed")
    stats = get_stats()
    return render_template("removed.html", repos=repos, stats=stats)


@app.route("/watched")
def watched():
    _ensure_db()
    filter_status = request.args.get("status")
    repos = list_repos(status=filter_status if filter_status in ("alive", "removed") else None)
    stats = get_stats()
    return render_template("watched.html", repos=repos, stats=stats, current_filter=filter_status)


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
    repos = list_repos(status="removed")
    return jsonify(repos)


@app.route("/api/watched")
def api_watched():
    _ensure_db()
    repos = list_repos()
    stats = get_stats()
    return jsonify({"repos": repos, "stats": stats})


def main():
    port = int(os.environ.get("PORT", 5000))
    _ensure_db()
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", False))
