from __future__ import annotations

from typing import Any
import base64
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from neuro_san.interfaces.coded_tool import CodedTool
from github_client import GitHubClient

ROOT = Path(os.getenv("NEURO_ROOT") or Path.cwd())
CACHE_DIR = ROOT / ".neuro_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DB = CACHE_DIR / "github_index.sqlite3"


def _owner(args: dict[str, Any]) -> str:
    return str(args.get("owner") or os.getenv("NEURO_GITHUB_OWNER") or "").strip()


def _repo(args: dict[str, Any]) -> str:
    return str(args.get("repo") or os.getenv("NEURO_GITHUB_REPO") or "").strip()


def _limit(args: dict[str, Any], default: int = 20, maximum: int = 100) -> int:
    try:
        value = int(args.get("limit", default))
    except Exception:
        value = default
    return max(1, min(value, maximum))


def _clean_path(path: str) -> str:
    return "/" + str(path or "").lstrip("/")


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(INDEX_DB)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            kind TEXT NOT NULL,
            key TEXT NOT NULL,
            url TEXT,
            observed_at REAL NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_records_repo_kind ON records(repo, kind)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_records_key ON records(repo, key)")
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(repo, kind, key, payload)")
    except sqlite3.OperationalError:
        pass
    return con


def _index_record(repo_full: str, kind: str, key: str, payload: Any, url: str | None = None) -> None:
    text_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    con = _db()
    con.execute(
        "INSERT INTO records(repo,kind,key,url,observed_at,payload) VALUES(?,?,?,?,?,?)",
        (repo_full, kind, key, url, time.time(), text_payload),
    )
    try:
        con.execute("INSERT INTO records_fts(repo,kind,key,payload) VALUES(?,?,?,?)", (repo_full, kind, key, text_payload))
    except sqlite3.OperationalError:
        pass
    con.commit()
    con.close()


def _index_many(repo_full: str, kind: str, items: list[Any], key_fn, url_fn=None) -> int:
    con = _db()
    now = time.time()
    rows = []
    fts_rows = []
    for item in items:
        key = str(key_fn(item))
        payload = json.dumps(item, ensure_ascii=False, separators=(",", ":"), default=str)
        url = url_fn(item) if url_fn else None
        rows.append((repo_full, kind, key, url, now, payload))
        fts_rows.append((repo_full, kind, key, payload))
    con.executemany(
        "INSERT INTO records(repo,kind,key,url,observed_at,payload) VALUES(?,?,?,?,?,?)", rows
    )
    try:
        con.executemany("INSERT INTO records_fts(repo,kind,key,payload) VALUES(?,?,?,?)", fts_rows)
    except sqlite3.OperationalError:
        pass
    con.commit()
    con.close()
    return len(rows)


async def _paginate(client: GitHubClient, path: str, params: dict[str, Any] | None = None, max_items: int = 100) -> list[Any]:
    params = dict(params or {})
    out: list[Any] = []
    page = 1
    while len(out) < max_items:
        p = dict(params)
        p["page"] = page
        p["per_page"] = min(100, max_items - len(out))
        data = await client.request("GET", path, params=p)
        if not isinstance(data, list):
            return data
        out.extend(data)
        if len(data) < p["per_page"]:
            break
        page += 1
    return out[:max_items]


def _repo_full(owner: str, repo: str) -> str:
    return f"{owner}/{repo}"


def _compact_item(item: Any) -> Any:
    if isinstance(item, list):
        return [_compact_item(x) for x in item[:100]]
    if not isinstance(item, dict):
        return item
    keep = {
        "id","node_id","number","name","full_name","path","type","sha","title",
        "message","description","state","status","conclusion","draft","login",
        "author","committer","user","created_at","updated_at","published_at","date",
        "html_url","url","default_branch","private","archived","language","stargazers_count",
        "watchers_count","forks_count","open_issues_count","size","visibility","head","base",
        "merged","mergeable","additions","deletions","changes","filename","tag_name","verified","reason"
    }
    out = {}
    for k in keep:
        if k in item:
            v = item[k]
            out[k] = _compact_item(v) if isinstance(v, (dict, list)) else v
    for k in ("stats", "labels"):
        if k in item:
            out[k] = _compact_item(item[k])
    return out


def _compact_list(items: Any, max_items: int = 100) -> list[Any]:
    return [_compact_item(x) for x in (items or [])[:max_items]]


def _commit_compact(item: dict[str, Any]) -> dict[str, Any]:
    c = item.get("commit") or {}
    a = c.get("author") or {}
    cm = c.get("committer") or {}
    return {
        "sha": item.get("sha"),
        "short_sha": (item.get("sha") or "")[:8],
        "message": (c.get("message") or "").splitlines()[0],
        "author": a.get("name"),
        "author_date": a.get("date"),
        "committer": cm.get("name"),
        "committer_date": cm.get("date"),
        "url": item.get("html_url"),
        "verified": (c.get("verification") or {}).get("verified"),
    }


def _commit_detail_compact(item: dict[str, Any], include_patch: bool = False) -> dict[str, Any]:
    c = item.get("commit") or {}
    a = c.get("author") or {}
    cm = c.get("committer") or {}
    files = []
    for f in (item.get("files") or [])[:200]:
        row = {
            "filename": f.get("filename"),
            "status": f.get("status"),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "changes": f.get("changes", 0),
            "blob_url": f.get("blob_url"),
        }
        if include_patch:
            row["patch"] = f.get("patch")
        files.append(row)
    return {
        "sha": item.get("sha"),
        "short_sha": (item.get("sha") or "")[:8],
        "message": (c.get("message") or "").splitlines()[0],
        "author": a.get("name"),
        "author_date": a.get("date"),
        "committer": cm.get("name"),
        "committer_date": cm.get("date"),
        "url": item.get("html_url"),
        "stats": item.get("stats") or {},
        "files_count": len(item.get("files") or []),
        "files": files,
    }


def _resource_compact(data: Any, max_items: int = 50) -> dict[str, Any]:
    if isinstance(data, list):
        return {"count": len(data), "items": _compact_list(data, max_items)}
    if isinstance(data, dict):
        return {"data": _compact_item(data)}
    return {"data": data}


def _model_result(source: str, **kwargs: Any) -> dict[str, Any]:
    result = {"tool_source": source}
    result.update(kwargs)
    return result


class GitHubBeast(CodedTool):
    """Broad GitHub control plane: high-level resources + arbitrary REST + GraphQL + local index."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        op = str(args.get("operation") or args.get("mode") or "").strip().lower()
        owner, repo = _owner(args), _repo(args)
        client = GitHubClient()
        full = _repo_full(owner, repo) if owner and repo else ""

        # Generic authenticated GitHub REST. This is the escape hatch for any endpoint
        # the PAT can access, including future GitHub APIs not hard-coded below.
        if op in {"rest_paginate", "paginate_rest"}:
            method = str(args.get("method") or "GET").upper()
            if method != "GET":
                raise ValueError("rest_paginate supports GET only")
            path = str(args.get("path") or "").strip()
            params = dict(args.get("params") or {})
            data = await _paginate(client, path, params, _limit(args, 100, 1000))
            return _model_result("GITHUB_BEAST_REST_PAGINATE", method=method, path=path, data=_resource_compact(data, 100))

        if op == "rest":
            method = str(args.get("method") or "GET").upper()
            path = str(args.get("path") or "").strip()
            params = args.get("params") or {}
            body = args.get("body")
            if not path.startswith("/"):
                path = "/" + path
            if method == "GET":
                data = await client.request("GET", path, params=params)
            elif method in {"POST", "PUT", "PATCH", "DELETE"}:
                data = await client.request(method, path, params=params, json=body)
            else:
                raise ValueError(f"Unsupported REST method: {method}")
            if owner and repo:
                _index_record(full, "rest:" + method.lower(), path, data, path)
            return _model_result("GITHUB_BEAST_REST", method=method, path=path, data=_resource_compact(data, 50))

        if op == "graphql":
            query = str(args.get("query") or "").strip()
            variables = args.get("variables") or {}
            if not query:
                raise ValueError("query is required")
            # Direct GraphQL endpoint using the GitHub token from github_client env.
            token = os.getenv("GITHUB_TOKEN", "").strip()
            if not token:
                raise RuntimeError("GITHUB_TOKEN is missing")
            req = urllib.request.Request(
                "https://api.github.com/graphql",
                data=json.dumps({"query": query, "variables": variables}).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "NeuroSAN/v17",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            if owner and repo:
                _index_record(full, "graphql", query[:180], data)
            return _model_result("GITHUB_BEAST_GRAPHQL", data=_resource_compact(data, 25))

        if op in {"index_search", "search_index"}:
            q = str(args.get("query") or "").strip()
            if not q:
                raise ValueError("query is required")
            repo_q = full or str(args.get("repository") or "").strip()
            con = _db()
            try:
                if repo_q:
                    rows = con.execute(
                        "SELECT kind,key,url,observed_at,payload FROM records WHERE repo=? AND payload LIKE ? ORDER BY observed_at DESC LIMIT ?",
                        (repo_q, f"%{q}%", _limit(args, 20, 200)),
                    ).fetchall()
                else:
                    rows = con.execute(
                        "SELECT kind,key,url,observed_at,payload FROM records WHERE payload LIKE ? ORDER BY observed_at DESC LIMIT ?",
                        (f"%{q}%", _limit(args, 20, 200)),
                    ).fetchall()
            finally:
                con.close()
            return {
                "tool_source": "GITHUB_LOCAL_INDEX",
                "database": str(INDEX_DB),
                "query": q,
                "results": [
                    {"kind": k, "key": key, "url": url, "observed_at": ts, "payload": json.loads(payload)}
                    for k, key, url, ts, payload in rows
                ],
            }

        if op in {"index_repo", "hydrate", "sync_repo"}:
            if not owner or not repo:
                raise ValueError("owner and repo are required")
            count = 0
            info = await client.request("GET", f"/repos/{owner}/{repo}")
            _index_record(full, "repo", full, info, info.get("html_url"))
            count += 1
            branch = info.get("default_branch") or "main"

            tree = await client.request(
                "GET", f"/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(branch, safe='')}",
                params={"recursive": "1"},
            )
            tree_items = tree.get("tree", []) if isinstance(tree, dict) else []
            count += _index_many(full, "tree", tree_items, lambda x: x.get("path", ""), lambda x: None)

            endpoints = [
                ("commits", f"/repos/{owner}/{repo}/commits"),
                ("pulls", f"/repos/{owner}/{repo}/pulls"),
                ("issues", f"/repos/{owner}/{repo}/issues"),
                ("releases", f"/repos/{owner}/{repo}/releases"),
                ("tags", f"/repos/{owner}/{repo}/tags"),
                ("branches", f"/repos/{owner}/{repo}/branches"),
                ("contributors", f"/repos/{owner}/{repo}/contributors"),
                ("collaborators", f"/repos/{owner}/{repo}/collaborators"),
                ("deployments", f"/repos/{owner}/{repo}/deployments"),
                ("milestones", f"/repos/{owner}/{repo}/milestones"),
                ("hooks", f"/repos/{owner}/{repo}/hooks"),
            ]
            for kind, path in endpoints:
                try:
                    data = await _paginate(client, path, {"state": "all"} if kind in {"pulls", "issues"} else {}, 100)
                    if isinstance(data, list):
                        count += _index_many(full, kind, data, lambda x, k=kind: x.get("id") or x.get("sha") or x.get("name") or str(x), lambda x: x.get("html_url"))
                except Exception:
                    # Indexing is opportunistic. The generic REST route remains the fallback.
                    continue
            try:
                runs = await client.request("GET", f"/repos/{owner}/{repo}/actions/runs", params={"per_page": 100})
                count += _index_many(full, "actions", runs.get("workflow_runs", []), lambda x: x.get("id"), lambda x: x.get("html_url"))
            except Exception:
                pass
            return {
                "tool_source": "GITHUB_BEAST_INDEX",
                "repository": full,
                "default_branch": branch,
                "records_indexed": count,
                "database": str(INDEX_DB),
            }

        if not owner and op not in {"repositories", "user", "orgs"}:
            raise ValueError("owner is required")

        # High-level direct operations.
        if op in {"repositories", "repos", "access"}:
            org = str(args.get("org") or "").strip()
            if org:
                data = await _paginate(client, f"/orgs/{urllib.parse.quote(org, safe='')}/repos", {"type": "all", "sort": "updated"}, _limit(args, 100, 100))
            else:
                data = await _paginate(client, "/user/repos", {"visibility": "all", "affiliation": "owner,collaborator,organization_member", "sort": "updated"}, _limit(args, 100, 100))
            return _model_result("GITHUB_BEAST_REPOSITORIES", count=len(data), repositories=_compact_list(data, 100))

        if op in {"user", "me"}:
            data = await client.request("GET", "/user")
            return _model_result("GITHUB_BEAST_USER", user=_compact_item(data))

        if op in {"repo", "repository", "metadata"}:
            data = await client.request("GET", f"/repos/{owner}/{repo}")
            _index_record(full, "repo", full, data, data.get("html_url"))
            return _model_result("GITHUB_BEAST_REPO", repository=_compact_item(data))

        if op in {"tree", "files", "file_tree"}:
            branch = str(args.get("branch") or "").strip()
            if not branch:
                info = await client.request("GET", f"/repos/{owner}/{repo}")
                branch = info.get("default_branch") or "main"
            data = await client.request("GET", f"/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(branch, safe='')}", params={"recursive": "1"})
            return _model_result("GITHUB_BEAST_TREE", branch=branch, truncated=data.get("truncated", False), count=len(data.get("tree", [])), paths=[{"path":x.get("path"),"type":x.get("type"),"sha":x.get("sha"),"size":x.get("size")} for x in data.get("tree", [])[:500]])

        if op in {"file", "read_file", "contents"}:
            path = str(args.get("path") or "").strip().lstrip("/")
            ref = str(args.get("ref") or args.get("branch") or "").strip()
            params = {"ref": ref} if ref else {}
            data = await client.request("GET", f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path, safe='/')}", params=params)
            if isinstance(data, dict) and data.get("content"):
                try:
                    data["decoded_content"] = base64.b64decode(data["content"].encode()).decode("utf-8", errors="replace")
                except Exception:
                    pass
            return _model_result("GITHUB_BEAST_FILE", path=data.get("path", path), sha=data.get("sha"), size=data.get("size"), url=data.get("html_url"), content=data.get("decoded_content"), download_url=data.get("download_url"))

        if op in {"search_code", "code_search"}:
            query = str(args.get("query") or "").strip()
            q = urllib.parse.quote(f"{query} repo:{owner}/{repo}", safe="")
            data = await client.request("GET", f"/search/code?q={q}")
            return _model_result("GITHUB_BEAST_CODE_SEARCH", total_count=data.get("total_count", 0), matches=[{"name":x.get("name"),"path":x.get("path"),"sha":x.get("sha"),"url":x.get("html_url")} for x in data.get("items", [])[:100]])

        if op in {"commits", "history"}:
            data = await _paginate(client, f"/repos/{owner}/{repo}/commits", {k: args[k] for k in ("sha", "path", "author", "since", "until") if args.get(k)}, _limit(args, 20, 100))
            return _model_result("GITHUB_BEAST_COMMITS", count=len(data), commits=[_commit_compact(x) for x in data[:100]])

        if op in {"commit", "commit_detail", "changed_files"}:
            sha = str(args.get("sha") or "").strip()
            data = await client.request("GET", f"/repos/{owner}/{repo}/commits/{urllib.parse.quote(sha, safe='')}")
            return _model_result("GITHUB_BEAST_COMMIT_DETAIL", commit=_commit_detail_compact(data, bool(args.get("include_patch"))))

        endpoint_map = {
            "prs": f"/repos/{owner}/{repo}/pulls",
            "pulls": f"/repos/{owner}/{repo}/pulls",
            "issues": f"/repos/{owner}/{repo}/issues",
            "releases": f"/repos/{owner}/{repo}/releases",
            "tags": f"/repos/{owner}/{repo}/tags",
            "branches": f"/repos/{owner}/{repo}/branches",
            "contributors": f"/repos/{owner}/{repo}/contributors",
            "collaborators": f"/repos/{owner}/{repo}/collaborators",
            "deployments": f"/repos/{owner}/{repo}/deployments",
            "milestones": f"/repos/{owner}/{repo}/milestones",
            "hooks": f"/repos/{owner}/{repo}/hooks",
            "environments": f"/repos/{owner}/{repo}/environments",
            "topics": f"/repos/{owner}/{repo}/topics",
            "languages": f"/repos/{owner}/{repo}/languages",
            "traffic_clones": f"/repos/{owner}/{repo}/traffic/clones",
            "traffic_views": f"/repos/{owner}/{repo}/traffic/views",
            "referrers": f"/repos/{owner}/{repo}/traffic/popular/referrers",
            "paths": f"/repos/{owner}/{repo}/traffic/popular/paths",
            "community_profile": f"/repos/{owner}/{repo}/community/profile",
            "participation": f"/repos/{owner}/{repo}/stats/participation",
            "commit_activity": f"/repos/{owner}/{repo}/stats/commit_activity",
            "contributors_stats": f"/repos/{owner}/{repo}/stats/contributors",
            "code_frequency": f"/repos/{owner}/{repo}/stats/code_frequency",
            "weekly_commit_activity": f"/repos/{owner}/{repo}/stats/commit_activity",
            "actions": f"/repos/{owner}/{repo}/actions/runs",
            "deployments_statuses": f"/repos/{owner}/{repo}/deployments",
            "comments": f"/repos/{owner}/{repo}/comments",
        }
        if op in endpoint_map:
            params = {}
            if op in {"prs", "pulls", "issues"}:
                params["state"] = str(args.get("state") or "all")
            data = await _paginate(client, endpoint_map[op], params, _limit(args, 50, 100))
            return _model_result("GITHUB_BEAST_RESOURCE", operation=op, data=_resource_compact(data, 100))

        if op in {"pr", "pull"}:
            number = int(args.get("number"))
            data = await client.request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
            return _model_result("GITHUB_BEAST_PR", pr=_compact_item(data))

        if op == "pr_files":
            number = int(args.get("number"))
            data = await _paginate(client, f"/repos/{owner}/{repo}/pulls/{number}/files", {}, 100)
            return _model_result("GITHUB_BEAST_PR_FILES", count=len(data), files=_compact_list(data, 200))

        if op in {"pr_reviews", "reviews"}:
            number = int(args.get("number"))
            data = await _paginate(client, f"/repos/{owner}/{repo}/pulls/{number}/reviews", {}, 100)
            return _model_result("GITHUB_BEAST_PR_REVIEWS", count=len(data), reviews=_compact_list(data, 100))

        if op in {"issue", "issue_detail"}:
            number = int(args.get("number"))
            data = await client.request("GET", f"/repos/{owner}/{repo}/issues/{number}")
            return _model_result("GITHUB_BEAST_ISSUE", issue=_compact_item(data))

        if op in {"issue_comments", "pr_comments"}:
            number = int(args.get("number"))
            if op == "pr_comments":
                path = f"/repos/{owner}/{repo}/issues/{number}/comments"
            else:
                path = f"/repos/{owner}/{repo}/issues/{number}/comments"
            data = await _paginate(client, path, {}, 100)
            return _model_result("GITHUB_BEAST_COMMENTS", count=len(data), comments=_compact_list(data, 100))

        raise ValueError(f"Unknown GitHubBeast operation: {op}")


class GitHubControlBeast(CodedTool):
    """Broad authenticated GitHub write surface. User has requested writes to be enabled by default."""
    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        owner, repo = _owner(args), _repo(args)
        action = str(args.get("action") or "").strip().lower()
        client = GitHubClient()
        if not owner or not repo:
            raise ValueError("owner and repo are required")

        if action in {"create_branch", "branch"}:
            branch = str(args.get("branch") or "").strip()
            base = str(args.get("base") or "").strip()
            if not base:
                info = await client.request("GET", f"/repos/{owner}/{repo}")
                base = info["default_branch"]
            ref = await client.request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{urllib.parse.quote(base, safe='')}")
            result = await client.request("POST", f"/repos/{owner}/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": ref["object"]["sha"]})
            return {"tool_source": "GITHUB_CONTROL_BEAST", "action": action, "result": result}

        if action in {"write_file", "update_file", "create_file"}:
            branch = str(args.get("branch") or "").strip()
            path = str(args.get("path") or "").strip().lstrip("/")
            content = str(args.get("content") or "")
            message = str(args.get("message") or f"Update {path}")
            current = None
            try:
                current = await client.request("GET", f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path, safe='/')}", params={"ref": branch})
            except Exception:
                pass
            body = {"message": message, "content": base64.b64encode(content.encode("utf-8")).decode(), "branch": branch}
            if current and current.get("sha"):
                body["sha"] = current["sha"]
            result = await client.request("PUT", f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path, safe='/')}", json=body)
            return {"tool_source": "GITHUB_CONTROL_BEAST", "action": action, "result": result, "commit_url": (result.get("commit") or {}).get("html_url")}

        if action in {"create_pr", "create_pull_request"}:
            info = await client.request("GET", f"/repos/{owner}/{repo}")
            body = {
                "title": str(args.get("title") or "Neuro SAN change"),
                "body": str(args.get("body") or ""),
                "head": str(args.get("head") or "").strip(),
                "base": str(args.get("base") or info["default_branch"]),
            }
            result = await client.request("POST", f"/repos/{owner}/{repo}/pulls", json=body)
            return {"tool_source": "GITHUB_CONTROL_BEAST", "action": action, "result": result, "pr_url": result.get("html_url")}

        if action in {"merge_pr", "merge_pull_request"}:
            number = int(args.get("number"))
            result = await client.request("PUT", f"/repos/{owner}/{repo}/pulls/{number}/merge", json={"merge_method": str(args.get("merge_method") or "squash")})
            return {"tool_source": "GITHUB_CONTROL_BEAST", "action": action, "result": result}

        if action in {"delete_file", "remove_file"}:
            path = str(args.get("path") or "").strip().lstrip("/")
            branch = str(args.get("branch") or "").strip()
            current = await client.request("GET", f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path, safe='/')}", params={"ref": branch})
            result = await client.request("DELETE", f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path, safe='/')}", json={"message": str(args.get("message") or f"Delete {path}"), "sha": current["sha"], "branch": branch})
            return {"tool_source": "GITHUB_CONTROL_BEAST", "action": action, "result": result}

        if action == "comment_issue":
            number = int(args.get("number"))
            result = await client.request("POST", f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": str(args.get("body") or "")})
            return {"tool_source": "GITHUB_CONTROL_BEAST", "action": action, "result": result}

        # Generic write passthrough for any PAT-authorized endpoint.
        method = str(args.get("method") or "POST").upper()
        path = str(args.get("path") or "").strip()
        body = args.get("body")
        if path:
            result = await client.request(method, path, json=body)
            return {"tool_source": "GITHUB_CONTROL_BEAST_GENERIC", "method": method, "path": path, "result": result}
        raise ValueError(f"Unknown GitHubControlBeast action: {action}")


class SentryBeast(CodedTool):
    """Broad Sentry API gateway plus common org/project/issue/event/release operations."""
    async def _request(self, method: str, path: str, body: Any = None, params: dict[str, Any] | None = None) -> Any:
        token = os.getenv("SENTRY_AUTH_TOKEN", "").strip() or os.getenv("SENTRY_TOKEN", "").strip()
        if not token:
            raise RuntimeError("SENTRY_AUTH_TOKEN is missing")
        base = os.getenv("SENTRY_API_BASE", "https://sentry.io/api/0").rstrip("/")
        url = base + (path if path.startswith("/") else "/" + path)
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "NeuroSAN/v17",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Sentry HTTP {e.code}: {raw[:1000]}")

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        op = str(args.get("operation") or args.get("action") or "").strip().lower()
        if op == "rest":
            method = str(args.get("method") or "GET").upper()
            path = str(args.get("path") or "")
            data = await self._request(method, path, args.get("body"), args.get("params"))
            return _model_result("SENTRY_BEAST_REST", method=method, path=path, data=_resource_compact(data, 50))

        org = str(args.get("org") or args.get("organization") or os.getenv("SENTRY_ORG") or "").strip()
        project = str(args.get("project") or os.getenv("SENTRY_PROJECT") or "").strip()
        issue = str(args.get("issue_id") or args.get("issue") or "").strip()
        event = str(args.get("event_id") or args.get("event") or "").strip()
        limit = _limit(args, 25, 100)

        paths = {
            "orgs": "/organizations/",
            "projects": f"/organizations/{org}/projects/" if org else "/organizations/",
            "teams": f"/organizations/{org}/teams/" if org else "/organizations/",
            "issues": f"/organizations/{org}/issues/" if org else "/organizations/",
            "releases": f"/organizations/{org}/releases/" if org else "/organizations/",
        }
        if op in paths:
            data = await self._request("GET", paths[op], params={"limit": limit})
            return _model_result("SENTRY_BEAST_RESOURCE", operation=op, data=_resource_compact(data, limit))

        if op in {"project", "project_detail"}:
            data = await self._request("GET", f"/projects/{org}/{project}/")
            return _model_result("SENTRY_BEAST_PROJECT", data=_resource_compact(data, 10))
        if op in {"project_issues", "project_issue_list"}:
            data = await self._request("GET", f"/projects/{org}/{project}/issues/", params={"limit": limit})
            return _model_result("SENTRY_BEAST_PROJECT_ISSUES", data=_resource_compact(data, limit))
        if op in {"issue", "issue_detail"}:
            data = await self._request("GET", f"/issues/{issue}/")
            return _model_result("SENTRY_BEAST_ISSUE", data=_resource_compact(data, 10))
        if op in {"issue_events", "events_for_issue"}:
            params = {k: args[k] for k in ("statsPeriod", "start", "end", "environment", "query", "full") if args.get(k) is not None}
            params["per_page"] = limit
            data = await self._request("GET", f"/organizations/{org}/issues/{issue}/events/", params=params)
            return _model_result("SENTRY_BEAST_ISSUE_EVENTS", data=_resource_compact(data, limit))
        if op in {"event", "event_detail"}:
            data = await self._request("GET", f"/projects/{org}/{project}/events/{event}/")
            return _model_result("SENTRY_BEAST_EVENT", data=_resource_compact(data, 10))
        if op in {"project_events", "events"}:
            params = {"limit": limit}
            for key in ("statsPeriod", "query", "environment"):
                if args.get(key) is not None:
                    params[key] = args[key]
            data = await self._request("GET", f"/organizations/{org}/issues/", params=params)
            return _model_result("SENTRY_BEAST_EVENTS", data=_resource_compact(data, limit))
        if op in {"org_releases", "releases"}:
            data = await self._request("GET", f"/organizations/{org}/releases/", params={"limit": limit})
            return _model_result("SENTRY_BEAST_RELEASES", data=_resource_compact(data, limit))
        if op in {"project_releases"}:
            data = await self._request("GET", f"/projects/{org}/{project}/releases/", params={"limit": limit})
            return _model_result("SENTRY_BEAST_PROJECT_RELEASES", data=_resource_compact(data, limit))
        if op in {"org_members", "members"}:
            data = await self._request("GET", f"/organizations/{org}/members/", params={"limit": limit})
            return _model_result("SENTRY_BEAST_MEMBERS", data=_resource_compact(data, limit))
        if op in {"integrations"}:
            data = await self._request("GET", f"/organizations/{org}/integrations/", params={"limit": limit})
            return _model_result("SENTRY_BEAST_INTEGRATIONS", data=_resource_compact(data, limit))
        raise ValueError(f"Unknown SentryBeast operation: {op}")



class EngineeringFastPath(CodedTool):
    """Execute common deterministic requests in code before using LLM reasoning."""
    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        mission = str(args.get("mission") or "").strip()
        low = mission.lower()
        owner = str(args.get("owner") or os.getenv("NEURO_GITHUB_OWNER") or "vinithreddybanda")
        repo = str(args.get("repo") or os.getenv("NEURO_GITHUB_REPO") or "activities")
        client = GitHubClient()

        if "discord" in low and any(x in low for x in ("send hi", "say hi", "send hello")):
            webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
            if not webhook:
                raise RuntimeError("DISCORD_WEBHOOK_URL is missing")
            message = "hi" if "hi" in low else "hello"
            req = urllib.request.Request(
                webhook + ("&" if "?" in webhook else "?") + "wait=true",
                data=json.dumps({"content": message, "allowed_mentions": {"parse": []}}).encode(),
                method="POST", headers={"Content-Type":"application/json","User-Agent":"NeuroSAN/v21"}
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                r.read()
                return {"tool_source":"FAST_PATH","handled":True,"operation":"discord_send","message":message,"status":r.status}

        if ("last commit" in low or "latest commit" in low) and any(x in low for x in ("id","sha","hash")):
            data = await client.request("GET", f"/repos/{owner}/{repo}/commits", params={"per_page":1})
            if not data:
                raise RuntimeError("GitHub returned no commits")
            return {"tool_source":"FAST_PATH","handled":True,"operation":"latest_commit","commit":_commit_compact(data[0])}

        if low in {"git url","github url","repo url","repository url"}:
            return {"tool_source":"FAST_PATH","handled":True,"operation":"repo_url","web_url":f"https://github.com/{owner}/{repo}","https_url":f"https://github.com/{owner}/{repo}.git","ssh_url":f"git@github.com:{owner}/{repo}.git"}

        return {"tool_source":"FAST_PATH","handled":False,"mission":mission}

class DiscordNotify(CodedTool):
    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        if not webhook:
            raise RuntimeError("DISCORD_WEBHOOK_URL is missing")
        op = str(args.get("operation") or "send").lower()
        message_id = str(args.get("message_id") or "").strip()
        url = webhook
        if message_id:
            url = webhook.rstrip("/") + f"/messages/{message_id}"

        if op == "send":
            body: dict[str, Any] = {"content": str(args.get("message") or "")[:1900], "allowed_mentions": {"parse": []}}
            if args.get("username") is not None: body["username"] = args["username"]
            if args.get("avatar_url") is not None: body["avatar_url"] = args["avatar_url"]
            if args.get("embeds") is not None: body["embeds"] = args["embeds"]
            if args.get("thread_id") is not None: url += "?thread_id=" + urllib.parse.quote(str(args["thread_id"]))
            elif args.get("thread_name") is not None: url += "?thread_name=" + urllib.parse.quote(str(args["thread_name"]))
            if "?" in url: url += "&wait=true"
            else: url += "?wait=true"
            method, data = "POST", body
        elif op == "edit":
            method, data = "PATCH", {"content": str(args.get("message") or "")[:1900]}
            if args.get("embeds") is not None: data["embeds"] = args["embeds"]
        elif op == "delete":
            method, data = "DELETE", None
        else:
            raise ValueError(f"Unknown Discord webhook operation: {op}")

        req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(), method=method, headers={"Content-Type": "application/json", "User-Agent": "NeuroSAN/v17"})
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return {"tool_source": "DISCORD_WEBHOOK", "operation": op, "sent": 200 <= response.status < 300, "status": response.status, "response": json.loads(raw) if raw else None}