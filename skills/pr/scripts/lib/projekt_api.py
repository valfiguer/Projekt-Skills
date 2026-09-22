"""projekt_api.py — shared Python client for Projekt skill scripts (stdlib only).

Targets the REWRITTEN /api/v1 API: org + project live in the PATH, and the resource
is `tasks`. Mirrors lib/http.sh: same auth precedence, headers,
rate-limit backoff, context cache and append-only ledger. Import from any script:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "projekt" / "scripts" / "lib"))
    from projekt_api import Client, Ledger, slim, eprint

    c = Client()                      # resolves token + org, raises with a hint if missing
    status, data = c.request(
        "GET", "/organizations/%s/projects/%s/tasks?limit=50" % (c.org, pid))
    rows = slim("task", data)

NEVER prints the token (only a fingerprint). The full spec is never touched here.
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error, pathlib, hashlib

DEFAULT_BASE = "https://api.projektrepublic.com/api/v1"
AUTH_FILE = pathlib.Path(os.environ.get("PJ_AUTH_FILE",
              str(pathlib.Path.home() / ".config" / "3xa-projekt" / "auth.json")))
RUN_DIR = pathlib.Path(os.environ.get("PJ_RUN_DIR", ".projekt-run"))
CONTEXT_FILE = RUN_DIR / "context.json"
MAX_RETRIES = int(os.environ.get("PJ_MAX_RETRIES", "5"))


def _normalize_base(base: str) -> str:
    """Accept a base written with or without the /v1 segment.

    A stored `api_base` of `https://api.projektrepublic.com/api` 404s EVERY call,
    and because the stored value wins over DEFAULT_BASE the failure looks like a
    dead API rather than a typo. Append the version instead of failing silently.
    """
    base = (base or "").rstrip("/")
    if base.endswith("/api"):
        base += "/v1"
    return base


def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


def _stored() -> dict:
    try:
        return json.loads(AUTH_FILE.read_text())
    except Exception:
        return {}


class Client:
    def __init__(self):
        s = _stored()
        self.token = os.environ.get("TREXA_API_TOKEN") or s.get("token")
        if not self.token:
            raise SystemExit("✗ No token. Set TREXA_API_TOKEN or create %s "
                             "(see references/auth-setup.md)." % AUTH_FILE)
        self.base = _normalize_base(os.environ.get("TREXA_API_BASE") or s.get("api_base") or DEFAULT_BASE)
        self.org = os.environ.get("TREXA_ORG_ID") or self._ctx("org_id")
        # project_id is self-discovered from /auth/me `api_key.project_id` for a
        # project-scoped PAT; cached in context.json by context_sync.sh.
        self.project = os.environ.get("TREXA_PROJECT_ID") or self._ctx("project_id")

    def _ctx(self, key):
        try:
            return json.loads(CONTEXT_FILE.read_text()).get(key)
        except Exception:
            return None

    def fingerprint(self) -> str:
        return "%s…%s" % (self.token[:9], self.token[-4:]) if self.token else "(none)"

    def request(self, method: str, path: str, body=None):
        """Return (status:int, data). Retries 429/5xx with header-driven backoff."""
        url = self.base + path
        payload = json.dumps(body).encode() if body is not None else None
        for attempt in range(1, MAX_RETRIES + 2):
            req = urllib.request.Request(url, data=payload, method=method)
            req.add_header("Authorization", "Bearer " + self.token)
            req.add_header("X-Auth-Token", self.token)          # LiteSpeed fallback
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json")
            if self.org:
                req.add_header("X-Org-Id", self.org)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, _parse(r.read())
            except urllib.error.HTTPError as e:
                status = e.code
                raw = e.read()
                if status == 429 or 500 <= status <= 599:
                    if attempt > MAX_RETRIES:
                        return status, _parse(raw)
                    wait = _backoff(e.headers, attempt)
                    eprint("  ⏳ %s on %s %s — retry %d/%d in %ds"
                           % (status, method, path, attempt, MAX_RETRIES, wait))
                    time.sleep(wait); continue
                return status, _parse(raw)
            except urllib.error.URLError as e:
                if attempt > MAX_RETRIES:
                    raise SystemExit("✗ Network error on %s %s: %s" % (method, path, e))
                time.sleep(attempt * attempt); continue

    def get_json(self, path):
        st, data = self.request("GET", path)
        if not (200 <= st < 300):
            raise SystemExit("✗ GET %s → %s: %s" % (path, st, _msg(data)))
        return data

    def context(self) -> dict:
        try:
            return json.loads(CONTEXT_FILE.read_text())
        except Exception:
            return {}


def _parse(raw: bytes):
    try:
        return json.loads(raw.decode() or "null")
    except Exception:
        return raw.decode(errors="replace")


def _msg(data):
    if isinstance(data, dict):
        return data.get("message") or data.get("error") or json.dumps(data)
    return str(data)


def _backoff(headers, attempt) -> int:
    try:
        ra = headers.get("Retry-After")
        if ra and int(ra) > 0:
            return min(int(ra), 120)
    except Exception:
        pass
    try:
        reset = headers.get("X-RateLimit-Reset")
        if reset:
            diff = int(reset) - int(time.time()) + 1
            if diff > 0:
                return min(diff, 120)
    except Exception:
        pass
    return attempt * attempt


# ── slim projections (mirror assets/slim.jq) ──
# /api/v1: tasks carry `reference` (PROJ-12) + `number`; status is one of
# todo|in_progress|done|cancelled. Time entries are ORG-scoped and use
# `minutes` + `entry_date`. Documents hold plain markdown in `content`.
def _task_view(o):
    return {"id": o.get("id"), "reference": o.get("reference"),
            "number": o.get("number"), "title": o.get("title"), "status": o.get("status"),
            "assignee_id": o.get("assignee_id"), "estimated_hours": o.get("estimated_hours"),
            "story_points": o.get("story_points"),
            "priority": o.get("priority"), "type": o.get("type")}


_VIEWS = {
    "task":    _task_view,
    "member":  lambda o: {"user_id": o.get("user_id") or o.get("id"), "name": o.get("name") or o.get("email"),
                          "role": o.get("role"), "expected_hours_per_week": o.get("expected_hours_per_week")},
    "project": lambda o: {k: o.get(k) for k in ("id", "key", "name", "status")},
    "time":    lambda o: {k: o.get(k) for k in ("id", "task_id", "task_reference", "user_id",
                                                "minutes", "entry_date", "is_billable")},
    "doc":     lambda o: {k: o.get(k) for k in ("id", "title", "parent_id", "project_id", "kind")},
}


def _rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "tasks", "projects", "members", "entries", "items", "rows", "groups"):
            if isinstance(data.get(k), list):
                return data[k]
    return None


def slim(view: str, data):
    fn = _VIEWS.get(view, lambda o: o)
    rows = _rows(data)
    if rows is not None:
        return [fn(o) for o in rows]
    return fn(data) if isinstance(data, dict) else data


# ── append-only ledger (mirror lib/run_ledger.sh; shares the same .jsonl files) ──
class Ledger:
    def __init__(self, path: str | None = None):
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        self.path = pathlib.Path(path or os.environ.get("PJ_LEDGER") or
                                 RUN_DIR / (time.strftime("%Y%m%d-%H%M%S") + ".jsonl"))
        self.path.touch()

    def add(self, phase, op, target, status, ref=None):
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "phase": phase, "op": op, "target": target, "status": status, "ref": ref}
        with self.path.open("a") as f:
            f.write(json.dumps(line) + "\n")

    def seen(self, op, key) -> bool:
        """True if a prior ok/created/updated line for (op,key) exists in ANY ledger."""
        for lf in RUN_DIR.glob("*.jsonl"):
            try:
                for ln in lf.read_text().splitlines():
                    if not ln.strip():
                        continue
                    r = json.loads(ln)
                    if r.get("op") == op and r.get("target") == key and r.get("status") in ("ok", "created", "updated"):
                        return True
            except Exception:
                continue
        return False

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        try:
            for ln in self.path.read_text().splitlines():
                if ln.strip():
                    s = json.loads(ln).get("status", "?")
                    counts[s] = counts.get(s, 0) + 1
        except Exception:
            pass
        return counts
