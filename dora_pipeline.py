from __future__ import annotations

import os
import sys
import time
import json
import math
import sqlite3
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

import requests
import json

UTC = timezone.utc
NOW_UTC = datetime.now(UTC)

# GitHub
GH_TOKEN       = os.getenv("GH_TOKEN") or ""
OWNER          = os.getenv("OWNER") or ""
REPO           = os.getenv("REPO") or ""
ENVIRONMENT    = os.getenv("ENVIRONMENT", "")
PR_LIMIT       = int(os.getenv("PR_LIMIT", "5000"))
DEPLOY_LIMIT   = int(os.getenv("DEPLOY_LIMIT", "5000"))

# Sentry
SENTRY_TOKEN   = os.getenv("SENTRY_TOKEN") or ""
SENTRY_ORG     = os.getenv("SENTRY_ORG") or ""
SENTRY_PROJECT = os.getenv("SENTRY_PROJECT") or ""

PROJECT_NAME = "backend" # filter sentry issues for perticular project

# Tunables
LOOKBACK_DAYS      = int(os.getenv("DAYS_LOOKBACK", "90"))
CFR_WINDOW_MIN     = int(os.getenv("CFR_WINDOW_MINUTES", "120"))

DB_PATH = os.getenv("DORA_DB_PATH", "dora.sqlite")

BASE_GH = "https://api.github.com"
BASE_SENTRY = "https://sentry.io/api/0"

HEADERS_GH = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

HEADERS_SENTRY = {"Authorization": f"Bearer {SENTRY_TOKEN}"} if SENTRY_TOKEN else None

SINCE_UTC = NOW_UTC - timedelta(days=LOOKBACK_DAYS)

# Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("dora")

def utc_from_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None

def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(UTC).isoformat() if dt else None

def sleep_until(ts_epoch: int):
    now = int(time.time())
    wait = max(0, ts_epoch - now) + 1
    if wait > 0:
        log.warning("Rate-limited. Sleeping %ss (until %s)", wait, datetime.fromtimestamp(ts_epoch, UTC))
        time.sleep(wait)

def _request_with_backoff(url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None) -> requests.Response:
    """HTTP GET with basic rate-limit handling and backoff."""
    backoff = 1.5
    attempts = 0
    while True:
        attempts += 1
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 403 and "X-RateLimit-Remaining" in r.headers:
            # GitHub rate limit
            try:
                remaining = int(r.headers.get("X-RateLimit-Remaining", "0"))
                reset = int(r.headers.get("X-RateLimit-Reset", "0"))
            except Exception:
                remaining, reset = 0, 0
            if remaining <= 0 and reset > 0:
                sleep_until(reset)
                continue
        if r.status_code in (429, 502, 503, 504):
            # generic backoff
            time.sleep(min(60, backoff))
            backoff *= 1.8
            if attempts <= 6:
                continue
        r.raise_for_status()
        return r

def gh_get(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    if not GH_TOKEN:
        raise RuntimeError("GH_TOKEN is required")
    r = _request_with_backoff(url, HEADERS_GH, params=params)
    return r.json()

def gh_get_paged(url: str, params: Optional[Dict[str, Any]] = None, cap_pages: int = 10) -> List[Any]:
    out: List[Any] = []
    page = 1
    params = dict(params or {})
    while page <= cap_pages:
        params.update({"per_page": 100, "page": page})
        r = _request_with_backoff(url, HEADERS_GH, params=params)
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out

def sentry_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    if not HEADERS_SENTRY:
        return None
    url = f"{BASE_SENTRY}{path}"
    r = _request_with_backoff(url, HEADERS_SENTRY, params=params)
    return r.json()

# DB setup

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS fact_deployment (
            deployment_id     INTEGER PRIMARY KEY,
            environment       TEXT,
            created_at_utc    TEXT,
            finished_at_utc   TEXT,
            state             TEXT,
            actor             TEXT,
            sha               TEXT,
            ref               TEXT,
            log_url           TEXT,
            source_fetched_at_utc TEXT,
            etl_run_id        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_fact_deployment_time ON fact_deployment(finished_at_utc);

        CREATE TABLE IF NOT EXISTS fact_pr (
            pr_number         INTEGER PRIMARY KEY,
            pr_merged_at_utc  TEXT,
            pr_merge_sha      TEXT,
            author            TEXT,
            source_fetched_at_utc TEXT,
            etl_run_id        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_fact_pr_merged_time ON fact_pr(pr_merged_at_utc);
        CREATE INDEX IF NOT EXISTS idx_fact_pr_sha ON fact_pr(pr_merge_sha);

        CREATE TABLE IF NOT EXISTS fact_incident (
            incident_id       TEXT PRIMARY KEY,
            title             TEXT,
            created_utc       TEXT,
            closed_utc        TEXT,
            duration_minutes  REAL,
            source_fetched_at_utc TEXT,
            etl_run_id        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_fact_incident_time ON fact_incident(created_utc);

        CREATE TABLE IF NOT EXISTS derived_deploy_window (
            window_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            prev_sha          TEXT,
            curr_sha          TEXT,
            deployed_at_utc   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_deploy_window_time ON derived_deploy_window(deployed_at_utc);

        CREATE TABLE IF NOT EXISTS derived_pr_lead_time (
            pr_number             INTEGER PRIMARY KEY,
            first_deployed_at_utc TEXT,
            lt_hours              REAL,
            window_prev_sha       TEXT,
            window_curr_sha       TEXT
        );

        CREATE TABLE IF NOT EXISTS derived_cfr_per_deploy (
            deployment_id     INTEGER PRIMARY KEY,
            failed            INTEGER,
            reason            TEXT
        );

        CREATE TABLE IF NOT EXISTS dora_summary_daily (
            date              TEXT PRIMARY KEY,
            deploys           INTEGER,
            failed_deploys    INTEGER,
            cfr               REAL,
            avg_lt_hours      REAL,
            mttr_min          REAL
        );

        CREATE TABLE IF NOT EXISTS dora_events (
            event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type    TEXT,   -- 'deployment' | 'pr_merge' | 'incident'
            when_utc      TEXT,
            sha           TEXT,
            pr_number     INTEGER,
            deployment_id INTEGER,
            incident_id   TEXT,
            title         TEXT,
            state         TEXT
        );
        """
    )
    conn.commit()

# 1) Ingest GitHub Deployments
def ingest_github_deployments(conn: sqlite3.Connection, etl_run_id: str) -> int:
    """
    Pull GitHub deployments for the specified ENVIRONMENT and write into fact_deployment.
    """
    params = {"environment": ENVIRONMENT, "per_page": 100}
    deployments = gh_get_paged(f"{BASE_GH}/repos/{OWNER}/{REPO}/deployments", params=params, cap_pages=10)
    if DEPLOY_LIMIT:
        deployments = deployments[:DEPLOY_LIMIT]

    cur = conn.cursor()
    ingested = 0
    for d in deployments:
        dep_id = d.get("id")
        ref = d.get("ref")
        sha = d.get("sha") or ref
        creator = (d.get("creator") or {}).get("login")
        created = utc_from_iso(d.get("created_at"))
        # Fetch latest status for this deployment
        statuses = gh_get_paged(f"{BASE_GH}/repos/{OWNER}/{REPO}/deployments/{dep_id}/statuses")
        latest = statuses[0] if statuses else None
        state = latest.get("state") if latest else "unknown"
        # Use the FIRST time the deployment hit success (so later 'inactive' won't break windows)
        success_ts = None
        for s in reversed(statuses):  # oldest → newest
            if s.get("state") == "success":
                success_ts = utc_from_iso(s.get("created_at"))
                break

        finished = success_ts or (utc_from_iso(latest.get("created_at")) if latest else None)
        log_url = latest.get("log_url") if latest else None

        cur.execute(
            """
            INSERT OR REPLACE INTO fact_deployment
            (deployment_id, environment, created_at_utc, finished_at_utc, state, actor, sha, ref, log_url, source_fetched_at_utc, etl_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dep_id,
                ENVIRONMENT,
                iso(created),
                iso(finished),
                state,
                creator,
                sha,
                ref,
                log_url,
                iso(NOW_UTC),
                etl_run_id,
            ),
        )
        ingested += 1
    conn.commit()
    log.info("Ingested %d GitHub deployments", ingested)
    return ingested

# 2) Ingest GitHub PRs (merged)
def ingest_github_prs(conn: sqlite3.Connection, etl_run_id: str) -> int:
    prs = gh_get_paged(f"{BASE_GH}/repos/{OWNER}/{REPO}/pulls", params={"state": "closed"}, cap_pages=10)
    prs = [p for p in prs if p.get("merged_at")]
    # Sort recent first, then cap
    prs.sort(key=lambda p: p.get("merged_at") or "", reverse=True)
    if PR_LIMIT:
        prs = prs[:PR_LIMIT]

    cur = conn.cursor()
    ingested = 0
    for p in prs:
        pr_number = p.get("number")
        merged_at = utc_from_iso(p.get("merged_at"))
        merge_sha = p.get("merge_commit_sha")
        author = (p.get("user") or {}).get("login")

        if merged_at and merged_at < SINCE_UTC:
            # keep only lookback window for speed; schema supports more if needed
            pass

        cur.execute(
            """
            INSERT OR REPLACE INTO fact_pr
            (pr_number, pr_merged_at_utc, pr_merge_sha, author, source_fetched_at_utc, etl_run_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                pr_number,
                iso(merged_at),
                merge_sha,
                author,
                iso(NOW_UTC),
                etl_run_id,
            ),
        )
        ingested += 1
    conn.commit()
    log.info("Ingested %d GitHub PRs (merged)", ingested)
    return ingested

# 3) Build Deployment Windows & Map PRs (Lead Time)
def gh_compare_commits(base_sha: str, head_sha: str) -> List[str]:
    """
    Returns the list of commits (SHAs) that are in base..head (exclusive of base)
    """
    url = f"{BASE_GH}/repos/{OWNER}/{REPO}/compare/{base_sha}...{head_sha}"
    try:
        data = gh_get(url)
        commits = data.get("commits", [])
        return [c.get("sha") for c in commits if c.get("sha")]
    except requests.HTTPError as e:
        log.warning("compare %s..%s failed: %s", base_sha, head_sha, e)
        return []

def build_deploy_windows_and_lt(conn: sqlite3.Connection) -> Tuple[int, int]:
    """
    Build windows from successive successful deployments.
    For each merged PR, find the first window in which its merge_commit_sha appears;
    compute lead time as first_deploy - merged_at.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sha, finished_at_utc FROM fact_deployment WHERE environment=? AND finished_at_utc IS NOT NULL ORDER BY finished_at_utc ASC
        """,
        (ENVIRONMENT,),
    )
    rows = cur.fetchall()
    if len(rows) < 2:
        log.warning("Not enough successful deployments to form windows (need >= 2).")
        cur.execute("DELETE FROM derived_deploy_window")
        cur.execute("DELETE FROM derived_pr_lead_time")
        conn.commit()
        return 0, 0

    # Windows: prev_success -> curr_success
    cur.execute("DELETE FROM derived_deploy_window")
    for i in range(1, len(rows)):
        prev_sha, _ = rows[i - 1]
        curr_sha, curr_finished = rows[i]
        cur.execute(
            "INSERT INTO derived_deploy_window (prev_sha, curr_sha, deployed_at_utc) VALUES (?, ?, ?)",
            (prev_sha, curr_sha, curr_finished),
        )
    conn.commit()

    # Cache compare results
    cur.execute("SELECT rowid, prev_sha, curr_sha, deployed_at_utc FROM derived_deploy_window ORDER BY deployed_at_utc ASC")
    windows = cur.fetchall()
    compare_cache: Dict[int, set] = {}
    for rowid, prev_sha, curr_sha, _ in windows:
        compare_cache[rowid] = set(gh_compare_commits(prev_sha, curr_sha))
    # Map PRs to first window containing its merge SHA
    cur.execute("SELECT pr_number, pr_merged_at_utc, pr_merge_sha FROM fact_pr")
    prs = cur.fetchall()

    cur.execute("DELETE FROM derived_pr_lead_time")
    mapped = 0
    for pr_number, merged_at_iso, pr_merge_sha in prs:
        if not pr_merge_sha or not merged_at_iso:
            continue
        merged_dt = utc_from_iso(merged_at_iso)
        first_deploy_time: Optional[datetime] = None
        first_window: Optional[Tuple[str, str]] = None

        for rowid, prev_sha, curr_sha, deployed_at_iso in windows:
            if pr_merge_sha in compare_cache.get(rowid, set()):
                first_deploy_time = utc_from_iso(deployed_at_iso)
                first_window = (prev_sha, curr_sha)
                break

        lt_hours = 0
        if first_deploy_time and merged_dt:
            lt_hours = round((first_deploy_time - merged_dt).total_seconds() / 3600.0, 2)

        cur.execute(
            """
            INSERT OR REPLACE INTO derived_pr_lead_time
            (pr_number, first_deployed_at_utc, lt_hours, window_prev_sha, window_curr_sha)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                pr_number,
                iso(first_deploy_time),
                lt_hours,
                first_window[0] if first_window else None,
                first_window[1] if first_window else None,
            ),
        )
        mapped += 1
    conn.commit()
    log.info("Built %d deployment windows, mapped LT for %d PRs", len(windows), mapped)
    return len(windows), mapped

# 4) CFR (Sentry-first, GH fallback)
def sentry_recent_releases_production() -> List[Dict[str, Any]]:
    """
    Optionally get Sentry releases and their production deploy times (if releases are used).
    Returns list of dicts: {"version": str, "deployed_at": datetime}
    """
    if not HEADERS_SENTRY:
        return []
    releases = sentry_get(f"/organizations/{SENTRY_ORG}/releases/", params={"per_page": 100}) or []
    out: List[Dict[str, Any]] = []
    for rel in releases:
        version = rel.get("version")
        try:
            deploys = sentry_get(f"/organizations/{SENTRY_ORG}/releases/{version}/deploys/") or []
        except Exception:
            deploys = []
        for d in deploys:
            if d.get("environment") != "production":
                print("environment",d.get("environment"))
                continue
            finished = d.get("dateFinished") or d.get("dateStarted")
            dt = utc_from_iso(finished)
            if dt and dt >= SINCE_UTC:
                out.append({"version": version, "deployed_at": dt})
    out.sort(key=lambda x: x["deployed_at"])
    return out

def sentry_incidents_in_window(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    if not HEADERS_SENTRY:
        return []
    try:
        incidents = sentry_get(f"/organizations/{SENTRY_ORG}/incidents/", params={"per_page": 100}) or []
    except Exception:
        return []
    found = []
    for inc in incidents:
        created = utc_from_iso(inc.get("dateCreated"))
        if created and start <= created <= end:
            found.append(inc)
    return found

def sentry_issues_in_window(start: datetime, end: datetime, version: Optional[str] = None) -> List[Dict[str, Any]]:
    if not HEADERS_SENTRY:
        return []
    start_s = start.strftime("%Y-%m-%dT%H:%M:%S")
    end_s = end.strftime("%Y-%m-%dT%H:%M:%S")
    q = f"environment:production firstSeen:>={start_s} firstSeen:<={end_s}"
    if version:
        q += f" release:{version}"
    try:
        issues = sentry_get(
            f"/organizations/{SENTRY_ORG}/issues/",
            params={"project": SENTRY_PROJECT, "query": q, "per_page": 50},
        ) or []
    except Exception:
        issues = []
    return issues

def compute_cfr_per_deploy(conn: sqlite3.Connection) -> int:
    """
    For each deployment (any state), decide failed=1/0 and reason.
    Primary signal: Sentry incidents/issues in [finished_at, finished_at + CFR_WINDOW_MIN].
    Fallback: GitHub state == 'failure'.
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM derived_cfr_per_deploy")

    # Precompute Sentry release-based windows (optional)
    sentry_rel_windows = sentry_recent_releases_production()  # may be empty if releases not used

    cur.execute(
        """
        SELECT deployment_id, finished_at_utc, state
        FROM fact_deployment
        WHERE environment=? AND finished_at_utc IS NOT NULL
        """,
        (ENVIRONMENT,),
    )
    deployments = cur.fetchall()
    classified = 0
    window_delta = timedelta(minutes=CFR_WINDOW_MIN)

    for dep_id, finished_iso, gh_state in deployments:
        finished = utc_from_iso(finished_iso)
        if not finished:
            continue
        start, end = finished, finished + window_delta

        failed = 0
        reason = "none"

        # Primary: Sentry signals by time
        incs = sentry_incidents_in_window(start, end) if HEADERS_SENTRY else []
        issues = sentry_issues_in_window(start, end) if HEADERS_SENTRY else []
        if incs or issues:
            failed, reason = 1, "sentry_window"
        # Else: if we have release data, check any release deployed close-by (heuristic)
        elif sentry_rel_windows:
            for rel in sentry_rel_windows:
                rel_dt = rel["deployed_at"]
                if start <= rel_dt <= end:
                    iss2 = sentry_issues_in_window(start, end, version=rel["version"])
                    if iss2:
                        failed, reason = 1, "sentry_window"
                        break
        # Fallback: GitHub status failure
        if not failed and (gh_state == "failure" or gh_state == "error"):
            failed, reason = 1, "gh_status_failure"

        cur.execute(
            "INSERT OR REPLACE INTO derived_cfr_per_deploy (deployment_id, failed, reason) VALUES (?, ?, ?)",
            (dep_id, failed, reason),
        )
        classified += 1

    conn.commit()
    log.info("Classified CFR for %d deployments", classified)
    return classified

# 5) MTTR from Sentry incidents
def ingest_sentry_incidents(conn: sqlite3.Connection, etl_run_id: str) -> int:
    if not HEADERS_SENTRY:
        log.info("Sentry credentials not provided; skipping incident ingestion.")
        return 0
    incidents = sentry_get(f"/organizations/{SENTRY_ORG}/issues/", params={"query": "is:resolved","per_page": 100}) or []
    cur = conn.cursor()
    ingested = 0
    for inc in incidents:
        created = utc_from_iso(inc.get("firstSeen"))
        closed = utc_from_iso(inc.get("lastSeen"))
        project = inc.get("project")
        if project.get("name") != PROJECT_NAME:
            continue
        if not created or not closed:
            continue
        if created < SINCE_UTC:
            # keep to recent; logic supports longer retention if needed
            pass
        duration = (closed - created).total_seconds() / 60.0
        cur.execute(
            """
            INSERT OR REPLACE INTO fact_incident
            (incident_id, title, created_utc, closed_utc, duration_minutes, source_fetched_at_utc, etl_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(inc.get("id")),
                inc.get("title", ""),
                iso(created),
                iso(closed),
                duration,
                iso(NOW_UTC),
                etl_run_id,
            ),
        )
        ingested += 1
    conn.commit()
    log.info("Ingested %d Sentry incidents", ingested)
    return ingested

# 6) Daily summary + unified events stream
def rebuild_daily_summary(conn: sqlite3.Connection):
    """
    Rebuild dora_summary_daily from facts & derived tables. SQLite-safe (no FULL OUTER JOIN).
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM dora_summary_daily")

    # Prepare sub-aggregations
    # Deployments (success/failure with finished time)
    cur.execute(
        """
        WITH deploys AS (
      SELECT date(substr(finished_at_utc,1,10)) AS day, COUNT(*) AS cnt
      FROM fact_deployment
      WHERE environment=? AND finished_at_utc IS NOT NULL
      GROUP BY 1)
        SELECT day, cnt FROM deploys
        """,
        (ENVIRONMENT,),
    )
    deploys = {row[0]: row[1] for row in cur.fetchall()}

    # Failed deploys
    cur.execute(
        """
        WITH fails AS (
          SELECT date(substr(fd.finished_at_utc,1,10)) AS day, SUM(dc.failed) AS failed
          FROM fact_deployment fd
          JOIN derived_cfr_per_deploy dc ON dc.deployment_id = fd.deployment_id
          WHERE fd.environment=? AND fd.finished_at_utc IS NOT NULL
          GROUP BY 1
        )
        SELECT day, failed FROM fails
        """,
        (ENVIRONMENT,),
    )
    failed_map = {row[0]: row[1] for row in cur.fetchall()}

    # Avg LT hours per day (by PR merge date)
    cur.execute(
        """
        WITH lt AS (
          SELECT date(substr(pr.pr_merged_at_utc,1,10)) AS day, SUM(d.lt_hours) AS avg_lt
          FROM fact_pr pr
          JOIN derived_pr_lead_time d USING(pr_number)
          WHERE d.lt_hours IS NOT NULL
          GROUP BY 1
        )
        SELECT day, avg_lt FROM lt
        """
    )
    lt_map = {row[0]: row[1] for row in cur.fetchall()}

    # MTTR minutes per day (by incident created date)
    cur.execute(
        """
        WITH mt AS (
          SELECT date(substr(created_utc,1,10)) AS day, SUM(duration_minutes) AS mttr
          FROM fact_incident
          GROUP BY 1
        )
        SELECT day, mttr FROM mt
        """
    )
    mttr_map = {row[0]: row[1] for row in cur.fetchall()}

    # Union all days present in any map
    all_days = set(deploys) | set(failed_map) | set(lt_map) | set(mttr_map)
    for day in sorted(all_days):
        dep = int(deploys.get(day, 0) or 0)
        fail = int(failed_map.get(day, 0) or 0)
        cfr = (fail / dep) if dep > 0 else 0
        lt = lt_map.get(day) if lt_map.get(day) != None else 0
        mt = mttr_map.get(day) if mttr_map.get(day) != None else 0
        cur.execute(
            """
            INSERT OR REPLACE INTO dora_summary_daily (date, deploys, failed_deploys, cfr, avg_lt_hours, mttr_min)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (day, dep, fail, cfr, lt, mt),
        )

    conn.commit()
    log.info("Rebuilt dora_summary_daily for %d days", len(all_days))

def backfill_events(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("DELETE FROM dora_events")
    # Deployments
    cur.execute(
        """
        INSERT INTO dora_events (event_type, when_utc, sha, deployment_id, state)
        SELECT 'deployment', finished_at_utc, sha, deployment_id, state
        FROM fact_deployment
        WHERE finished_at_utc IS NOT NULL
        """
    )
    # PR merges
    cur.execute(
        """
        INSERT INTO dora_events (event_type, when_utc, sha, pr_number)
        SELECT 'pr_merge', pr_merged_at_utc, pr_merge_sha, pr_number
        FROM fact_pr
        """
    )
    # Incidents
    cur.execute(
        """
        INSERT INTO dora_events (event_type, when_utc, incident_id, title)
        SELECT 'incident', created_utc, incident_id, title
        FROM fact_incident
        """
    )
    conn.commit()
    log.info("Backfilled dora_events")

def export_all_to_json(conn: sqlite3.Connection, output_file: str = "dora.json"):
    tables = [
        "fact_deployment",
        "fact_pr",
        "fact_incident",
        "derived_deploy_window",
        "derived_pr_lead_time",
        "derived_cfr_per_deploy",
        "dora_summary_daily",
        "dora_events",
    ]
    
    all_data = {}
    for table in tables:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        all_data[table] = [dict(zip(columns, row)) for row in rows]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=4)
    log.info("Exported all tables to JSON: %s", output_file)

# main function
def main():
    # Basic validation
    missing = []
    for var in ("GH_TOKEN", "OWNER", "REPO"):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        log.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(2)

    etl_run_id = f"run-{int(time.time())}"

    conn = db_connect()
    try:
        init_schema(conn)

        log.info("Ingesting GitHub deployments (env=%s)…", ENVIRONMENT)
        ingest_github_deployments(conn, etl_run_id)

        log.info("Ingesting GitHub PRs…")
        ingest_github_prs(conn, etl_run_id)

        log.info("Building deploy windows & mapping PRs (Lead Time)…")
        build_deploy_windows_and_lt(conn)

        if SENTRY_TOKEN and SENTRY_ORG and SENTRY_PROJECT:
            log.info("Ingesting Sentry incidents (for MTTR)…")
            ingest_sentry_incidents(conn, etl_run_id)
        else:
            log.info("Sentry credentials incomplete; skipping incident ingestion.")

        log.info("Computing CFR per deploy (Sentry-first, GH fallback)…")
        compute_cfr_per_deploy(conn)

        log.info("Rebuilding daily summary & events stream…")
        rebuild_daily_summary(conn)
        backfill_events(conn)

        log.info("✅ Done. SQLite file -> %s", DB_PATH)

        log.info("Exporting all tables to JSON…")
        export_all_to_json(conn, output_file="dora.json")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
