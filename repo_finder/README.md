# Repo Finder

Find source code for deleted or taken-down git repositories. Searches multiple
archive sources, monitors repos at scale, and detects when they disappear.

## Quickstart

```bash
# Install
pip install httpx flask

# Search for a deleted repo
python -m repo_finder octocat/hello-world

# Search by URL (GitHub, GitLab, Bitbucket, Codeberg, SourceHut)
python -m repo_finder https://gitlab.com/some-user/deleted-project

# Get JSON output
python -m repo_finder octocat/hello-world --json

# Download the best available copy
python -m repo_finder octocat/hello-world -d ./recovered

# Start the web interface
python -c "from repo_finder.web.app import app; app.run()" 
# Open http://localhost:5000

# Discover all GitHub repos with >10 stars and monitor them
export GITHUB_TOKEN=ghp_your_token_here
python -m repo_finder.scanner discover
python -m repo_finder.scanner scan
```

---

## Table of Contents

- [Installation](#installation)
- [CLI Search Tool](#cli-search-tool)
- [Web Interface](#web-interface)
- [Scanner & Discovery](#scanner--discovery)
- [Sources Searched](#sources-searched)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Cron Setup](#cron-setup)
- [How Discovery Works](#how-discovery-works)

---

## Installation

**Requirements:** Python 3.11+

```bash
pip install httpx flask
```

`httpx` is the only dependency for the CLI search tool. `flask` is needed for
the web interface.

---

## CLI Search Tool

Search for archived copies of a repository across 6 source categories.

```
python -m repo_finder <repo> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `repo` | `owner/repo` (assumes GitHub) or full URL from any git host |
| `--token TOKEN` | GitHub personal access token (or set `GITHUB_TOKEN`) |
| `--download DIR`, `-d DIR` | Download/clone best available copy to DIR |
| `--json` | Output results as JSON |
| `--sources SRC [SRC...]` | Only search specific sources (see below) |
| `--timeout N` | HTTP timeout in seconds (default: 30) |

### Source Names

Use these with `--sources` to search specific sources only:

| Name | Source |
|---|---|
| `forks` | GitHub fork search (API + search fallback) |
| `mirrors` | GitLab, GitHub, Codeberg, Bitbucket, SourceHut |
| `wayback` | Internet Archive Wayback Machine |
| `swh` | Software Heritage Archive |
| `packages` | npm, PyPI, crates.io, RubyGems |
| `google` | Google Cache (manual URL suggestion) |

### Examples

**Basic search (assumes GitHub):**
```bash
python -m repo_finder torvalds/linux
```

**Search for a GitLab project:**
```bash
python -m repo_finder https://gitlab.com/inkscape/inkscape
```

**Search for a Bitbucket repo:**
```bash
python -m repo_finder https://bitbucket.org/atlassian/python-bitbucket
```

**Only search forks and Software Heritage:**
```bash
python -m repo_finder octocat/hello-world --sources forks swh
```

**Get JSON output for scripting:**
```bash
python -m repo_finder octocat/hello-world --json | jq '.results[].clone_url'
```

**Download the best available copy:**
```bash
python -m repo_finder octocat/hello-world -d ./recovered-repo
```
This prefers cloneable sources (forks, mirrors) over tarballs (package
registries) over HTML-only archives (Wayback). If `git` is available, it
clones directly. Otherwise it downloads and extracts a tarball.

**Use a GitHub token for better rate limits:**
```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
python -m repo_finder some-user/deleted-project
```

### Output

Results are grouped by confidence level:

- **HIGH** — Full git repos (forks, mirrors, Software Heritage)
- **MEDIUM** — Partial archives (Wayback snapshots, package tarballs)
- **LOW** — Manual suggestions (Google Cache URLs)

```
=== Searching for copies of https://github.com/example/deleted-repo ===

  [HIGH] confidence

    GitHub Fork: user123/deleted-repo
      Fork by user123 (5 stars)
      URL: https://github.com/user123/deleted-repo
      Clone: git clone https://github.com/user123/deleted-repo.git
      Snapshot: 2024-03-15T10:30:00Z

    Software Heritage Archive
      Full source code preserved in Software Heritage
      URL: https://archive.softwareheritage.org/browse/origin/directory/...
      Snapshot: 2024-01-20

  [MEDIUM] confidence

    Wayback Machine
      Archived GitHub page (12 snapshots found)
      URL: https://web.archive.org/web/20240301.../https://github.com/example/deleted-repo
      Snapshot: 2024-03-01

Found 3 result(s) across 3 source(s).
```

---

## Web Interface

A browser-based UI with three pages: Search, Removed, and Watched.

### Starting the Server

```bash
python -c "from repo_finder.web.app import app; app.run()"
```

Or with custom port and debug mode:

```bash
PORT=8080 FLASK_DEBUG=1 python -c "from repo_finder.web.app import app; app.run()"
```

### Pages

| URL | Description |
|---|---|
| `/` | Search box — enter any repo URL or `owner/repo` |
| `/search?q=owner/repo` | Search results page |
| `/removed` | Dashboard of repos detected as taken down |
| `/watched` | All monitored repos with star counts and status |

The **Removed** page shows repos that were being watched and have since
returned 404/410/451. Each removed repo has a "Find archives" button that
runs a full recovery search.

The **Watched** page shows all monitored repos sorted by stars. You can
filter by status (alive/removed) and add repos directly via the form.
Pagination is automatic at 50 repos per page.

---

## Scanner & Discovery

The scanner system discovers repos, stores them in a local SQLite database,
and periodically checks if they're still alive.

```
python -m repo_finder.scanner <command> [options]
```

### Commands

#### `discover` — Crawl GitHub for repos with >N stars

```bash
python -m repo_finder.scanner discover [options]
```

| Flag | Default | Description |
|---|---|---|
| `--min-stars N` | 10 | Minimum star count threshold |
| `--token TOKEN` | — | GitHub token (or set `GITHUB_TOKEN`) |
| `--start DATE` | auto-resume | Start date (YYYY-MM-DD) |
| `--end DATE` | today | End date (YYYY-MM-DD) |

**Examples:**

```bash
# Discover all repos with >10 stars (resumes from last position)
python -m repo_finder.scanner discover --token $GITHUB_TOKEN

# Only repos with >1000 stars (faster, fewer repos)
python -m repo_finder.scanner discover --min-stars 1000

# Crawl a specific date range
python -m repo_finder.scanner discover --start 2023-01-01 --end 2023-12-31

# Re-crawl from scratch
python -m repo_finder.scanner discover --start 2008-01-01
```

Discovery is **resumable** — it saves progress after each week-chunk and picks
up where it left off on the next run. First run starts from 2008-01-01 (GitHub
launch). Subsequent runs continue from the last crawled date.

A GitHub token is strongly recommended. Without one, you're limited to 10
search requests per minute. With a token, 30 per minute.

#### `scan` — Check watched repos for removal

```bash
python -m repo_finder.scanner scan [options]
```

| Flag | Default | Description |
|---|---|---|
| `--token TOKEN` | — | GitHub token (or set `GITHUB_TOKEN`) |
| `--limit N` | 1000 | Max repos to check per run |
| `--quiet`, `-q` | false | Only print removals |

Checks repos in order of staleness (least recently checked first). A repo is
marked as "removed" when it returns HTTP 404, 410, or 451.

**Examples:**

```bash
# Check the 1000 stalest repos
python -m repo_finder.scanner scan --token $GITHUB_TOKEN

# Check more repos per run
python -m repo_finder.scanner scan --limit 5000

# Quiet mode — only prints when a removal is detected
python -m repo_finder.scanner scan --limit 5000 --quiet
```

#### `add` — Manually add repos to the watch list

```bash
python -m repo_finder.scanner add <url> [<url>...]
```

**Examples:**

```bash
# Add individual repos
python -m repo_finder.scanner add torvalds/linux https://gitlab.com/inkscape/inkscape

# Add a repo with full URL
python -m repo_finder.scanner add https://github.com/some-org/some-repo
```

#### `import` — Bulk import from a file

```bash
python -m repo_finder.scanner import <file>
```

The file should contain one repo URL or `owner/repo` per line. Lines starting
with `#` and blank lines are ignored.

**Example file (repos.txt):**
```
# Popular projects
torvalds/linux
https://github.com/rust-lang/rust
https://gitlab.com/inkscape/inkscape

# Forks to watch
user123/interesting-fork
```

```bash
python -m repo_finder.scanner import repos.txt
```

#### `list` — Display watched repos

```bash
python -m repo_finder.scanner list [options]
```

| Flag | Default | Description |
|---|---|---|
| `--removed` | — | Show only removed repos |
| `--alive` | — | Show only alive repos |
| `--limit N` | 50 | Max repos to display |

**Examples:**

```bash
# Show top 50 repos by stars
python -m repo_finder.scanner list

# Show only removed repos
python -m repo_finder.scanner list --removed

# Show more results
python -m repo_finder.scanner list --limit 200
```

**Output:**
```
  [X] https://github.com/example/deleted-repo (342 stars) removed 2024-06-15 checked 2024-06-15
  [.] https://github.com/torvalds/linux (54072 stars) checked 2024-06-15
  [.] https://github.com/rust-lang/rust (40571 stars) checked 2024-06-15

  Total: 12345 | Alive: 12300 | Removed: 45
```

`[X]` = removed, `[.]` = alive.

#### `stats` — Summary statistics

```bash
python -m repo_finder.scanner stats
```

**Output:**
```
Watched repos: 12345
  Alive:   12300
  Removed: 45
  Discovery crawled through: 2024-06-15
```

---

## Sources Searched

### GitHub Forks (source: `forks`)

Searches for surviving forks of a deleted GitHub repo. Two strategies:

1. **Forks API** — `GET /repos/{owner}/{repo}/forks` (works if repo or its
   redirect still exists)
2. **Search API fallback** — `GET /search/repositories?q={repo}+fork:only`
   with heuristic matching on parent/source name

Only active for GitHub URLs. Returns up to 10 forks.

### Git Mirrors (source: `mirrors`)

Checks if the same `owner/repo` exists on other platforms:

- **GitHub** — `api.github.com/repos/{owner}/{repo}`
- **GitLab** — `gitlab.com/api/v4/projects/{owner}%2F{repo}`
- **Codeberg** — `codeberg.org/api/v1/repos/{owner}/{repo}`
- **Bitbucket** — `api.bitbucket.org/2.0/repositories/{owner}/{repo}`
- **SourceHut** — `git.sr.ht/~{owner}/{repo}` (HTML check)

Automatically skips whichever platform the input URL came from.

### Wayback Machine (source: `wayback`)

Queries the Internet Archive's CDX API for archived snapshots:

- Archived repo pages at the original URL
- Raw file content (GitHub-specific: `raw.githubusercontent.com`)
- Archive downloads (`/archive/*`, `codeload.github.com`)
- GitLab/Codeberg archive downloads (`/-/archive/*`)

### Software Heritage (source: `swh`)

Checks if the repo was preserved in the [Software Heritage
Archive](https://archive.softwareheritage.org/), which periodically crawls
GitHub, GitLab, and other forges.

- Looks up the origin URL
- Gets visit history and snapshot IDs
- Provides browse URL and vault download link

Works for any platform URL, not just GitHub. Rate limit: 120 requests/hour
unauthenticated.

### Package Registries (source: `packages`)

Checks if a package with the same name as the repo exists and links back to
the origin URL:

- **npm** — `registry.npmjs.org/{repo}`
- **PyPI** — `pypi.org/pypi/{repo}/json`
- **crates.io** — `crates.io/api/v1/crates/{repo}`
- **RubyGems** — `rubygems.org/api/v1/gems/{repo}.json`

Returns download URLs for source tarballs when found.

### Google Cache (source: `google`)

Attempts to fetch Google's cached version of the repo page. Often blocked by
automated access, so it falls back to providing a manual search URL:

```
https://www.google.com/search?q=cache:github.com/owner/repo
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `GITHUB_TOKEN` | GitHub personal access token for API requests | — |
| `REPOFINDER_DB` | Path to SQLite database file | `./repofinder.db` |
| `PORT` | Web server port | `5000` |
| `FLASK_DEBUG` | Enable Flask debug mode | `false` |

---

## API Reference

The web interface exposes JSON API endpoints:

### `GET /api/search?q=<repo>`

Search for archived copies of a repo.

```bash
curl "http://localhost:5000/api/search?q=octocat/hello-world"
```

**Response:**
```json
{
  "error": null,
  "info": {
    "owner": "octocat",
    "repo": "hello-world",
    "platform": "github",
    "origin_url": "https://github.com/octocat/hello-world"
  },
  "results": [
    {
      "source_name": "Software Heritage Archive",
      "url": "https://archive.softwareheritage.org/browse/...",
      "description": "Full source code preserved in Software Heritage",
      "clone_url": null,
      "confidence": "high",
      "timestamp": "2024-01-20"
    }
  ],
  "source_count": 3
}
```

### `GET /api/removed?page=1&limit=50`

List repos detected as removed.

```bash
curl "http://localhost:5000/api/removed"
```

**Response:**
```json
{
  "repos": [
    {
      "id": 42,
      "owner": "example",
      "repo": "deleted-project",
      "platform": "github",
      "origin_url": "https://github.com/example/deleted-project",
      "status": "removed",
      "stars": 342,
      "first_seen": "2024-01-01T00:00:00+00:00",
      "last_checked": "2024-06-15T12:00:00+00:00",
      "removed_at": "2024-06-15T12:00:00+00:00"
    }
  ],
  "total": 45,
  "page": 1
}
```

### `GET /api/watched`

List all watched repos with stats.

```bash
curl "http://localhost:5000/api/watched"
```

---

## Cron Setup

For continuous monitoring, set up cron jobs:

```bash
# Edit crontab
crontab -e
```

```cron
# Discover new repos daily at 2 AM (catches up from last crawled date)
0 2 * * * cd /path/to/repo && python -m repo_finder.scanner discover --token $GITHUB_TOKEN >> /var/log/repo-discover.log 2>&1

# Scan 5000 repos for removal every 6 hours
0 */6 * * * cd /path/to/repo && python -m repo_finder.scanner scan --limit 5000 --quiet --token $GITHUB_TOKEN >> /var/log/repo-scan.log 2>&1
```

### Estimating Crawl Time

Discovery speed depends on your GitHub token:

| Token | Rate | Speed |
|---|---|---|
| No token | 10 searches/min | ~600 repos/min |
| Personal token | 30 searches/min | ~1,800 repos/min |

A full crawl from 2008 to present with `--min-stars 10` takes several days
with a token. With `--min-stars 100`, it takes hours. Progress is saved
automatically, so you can stop and resume at any time.

---

## How Discovery Works

The GitHub Search API returns at most 1,000 results per query. To enumerate
millions of repos above a star threshold, the crawler uses layered partitioning:

1. **Week chunks** — queries one week at a time:
   `stars:>10 created:2024-01-01..2024-01-07`

2. **Date binary split** — if a week returns >1,000 results, it splits into
   two halves and retries each separately

3. **Star range subdivision** — if a single day still has >1,000 results (e.g.,
   a popular launch day), it partitions by exponential star ranges:
   `stars:11..20`, `stars:21..50`, `stars:51..100`, etc.

4. **Full pagination** — for each query under the 1,000-result cap, it
   paginates through all pages (100 results per page, up to 10 pages)

This guarantees coverage of every repo above the threshold regardless of how
many were created on any given day.

### Database

All data is stored in a SQLite database (`repofinder.db` by default):

- **watched_repos** — all discovered/added repos with owner, repo, platform,
  stars, status (alive/removed), and timestamps
- **scan_log** — history of every scan check with HTTP status codes
- **discover_state** — crawl progress (last crawled date) for resumability
