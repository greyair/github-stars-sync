"""Sync managed GitHub repositories and the Notion dashboard. Standard library only."""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

NOTION = "https://api.notion.com/v1"
GITHUB = "https://api.github.com"
PROJECTS = os.environ.get("NOTION_PROJECTS_DATA_SOURCE_ID", "6c2c8677-6f57-41df-8d42-15cd72c2fcea")
REPOS = os.environ.get("NOTION_REPOS_DATA_SOURCE_ID", "fcab103c-0318-451d-b9b8-8410dc8c0752")
HOME = os.environ.get("NOTION_DASHBOARD_PAGE_ID", "3de41bef-3e24-81dc-a0df-e891cc9e001c")
OWNER = os.environ.get("GITHUB_OWNER", "greyair")
TOPIC = os.environ.get("GITHUB_DISCOVERY_TOPIC", "notion-managed")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
WARNINGS = []

def api(method, base, path, token, payload=None, params=None):
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    head = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json" if base == GITHUB else "application/json", "User-Agent": "notion-project-dashboard-sync/1.0"}
    if base == GITHUB:
        head["X-GitHub-Api-Version"] = "2022-11-28"
    else:
        head["Notion-Version"] = "2026-03-11"
    data = None
    if payload is not None:
        head["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers=head, method=method)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                body = resp.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) or (base == GITHUB and e.code == 403 and e.headers.get("Retry-After")):
                if attempt < 4:
                    time.sleep(min(2 ** attempt * 2, 25))
                    continue
            raise RuntimeError(f"{method} {path}: HTTP {e.code}: {body[:300]}") from e
    raise RuntimeError("Retry exhausted: " + path)

def github(method, path, payload=None, params=None):
    return api(method, GITHUB, path, os.environ["GH_PROJECTS_TOKEN"], payload, params)

def notion(method, path, payload=None, params=None):
    return api(method, NOTION, path, os.environ["NOTION_TOKEN"], payload, params)

def paginate_notion(source):
    result, cursor = [], None
    while True:
        q = {"page_size": 100}
        if cursor:
            q["start_cursor"] = cursor
        data = notion("POST", f"/data_sources/{source}/query", q)
        result.extend(data.get("results", []))
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor:
            return result

def paginate_github(path, params=None):
    result = []
    for page in range(1, 101):
        p = dict(params or {}, per_page=100, page=page)
        batch = github("GET", path, params=p)
        if not isinstance(batch, list):
            raise RuntimeError("Expected list for " + path)
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError("GitHub page limit reached: " + path)

def rich(value):
    return {"rich_text": [{"type": "text", "text": {"content": str(value)[:2000]}}]}

def title(value):
    return {"title": [{"type": "text", "text": {"content": str(value)[:2000]}}]}

def date(value):
    return {"date": {"start": value}} if value else {"date": None}

def textval(prop):
    return "".join(x.get("plain_text", x.get("text", {}).get("content", "")) for x in (prop.get("title") or prop.get("rich_text") or []))

def prop(page, name):
    return (page.get("properties") or {}).get(name) or {}

def url_repo(value):
    if not value:
        return None
    m = re.fullmatch(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", value.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None

def links(value):
    return list(dict.fromkeys(url_repo(x) for x in re.findall(r"https?://github\.com/[^\s,;，；<>]+", value) if url_repo(x)))

def related(page, name):
    return [x["id"] for x in prop(page, name).get("relation", []) if x.get("id")]

def update(page_id, props):
    if not props:
        return
    if DRY_RUN:
        print("DRY_RUN page", page_id, sorted(props))
    else:
        notion("PATCH", f"/pages/{page_id}", {"properties": props})

def create(props):
    if DRY_RUN:
        print("DRY_RUN create", textval(props["仓库名称"]))
        return None
    return notion("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": REPOS}, "properties": props})

def blocks(block_id):
    out, cursor = [], None
    while True:
        q = {"page_size": 100}
        if cursor:
            q["start_cursor"] = cursor
        result = notion("GET", f"/blocks/{block_id}/children", params=q)
        out.extend(result.get("results", []))
        cursor = result.get("next_cursor")
        if not result.get("has_more") or not cursor:
            return out

def block_text(block):
    typ = block.get("type", "")
    return "".join(t.get("plain_text", t.get("text", {}).get("content", "")) for t in block.get(typ, {}).get("rich_text", []))

def dashboard_stats(projects, repos):
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for p in projects:
        val = (prop(p, "执行优先级").get("select") or {}).get("name")
        if val in counts:
            counts[val] += 1
    graded = sum(counts.values())
    return {"项目总数": len(projects), "仓库总数": len(repos), "已分级项目": graded}, counts

def update_dashboard(projects, repos):
    stats, counts = dashboard_stats(projects, repos)
    # Preserve existing layout, headings and colours. Change only numeric headline blocks.
    found = set()
    stack = [(HOME, 0)]
    while stack:
        parent, depth = stack.pop()
        if depth > 5:
            continue
        for block in blocks(parent):
            kind = block.get("type")
            if kind == "callout":
                richitems = block.get("callout", {}).get("rich_text", [])
                header = "".join(t.get("plain_text", "") for t in richitems)
                if header in stats and header not in found:
                    found.add(header)
                    children = blocks(block["id"]) if block.get("has_children") else []
                    headline = next((c for c in children if c.get("type") in ("heading_1", "heading_2", "heading_3")), None)
                    if headline:
                        size = headline["type"]
                        if block_text(headline) != str(stats[header]):
                            if DRY_RUN:
                                print("DRY_RUN headline", header, stats[header])
                            else:
                                notion("PATCH", f"/blocks/{headline['id']}", {size: rich(str(stats[header]))})
                    else:
                        WARNINGS.append(f"Dashboard {header}: heading child not found")
                    # Third card includes priority breakdown; update only if it is a separate paragraph.
                    if header == "已分级项目":
                        value = "P0 {P0} · P1 {P1} · P2 {P2} · P3 {P3}".format(**counts)
                        for c in children:
                            if c.get("type") == "paragraph" and re.search(r"P0\s*\d+", block_text(c)):
                                if block_text(c) != value:
                                    if not DRY_RUN:
                                        notion("PATCH", f"/blocks/{c['id']}", {"paragraph": rich(value)})
                                break
            if block.get("has_children") and kind != "callout":
                stack.append((block["id"], depth + 1))
    for label in stats:
        if label not in found:
            WARNINGS.append(f"Dashboard card missing: {label}")

def discover(projects, repo_pages):
    managed = {}
    for page in repo_pages:
        name = url_repo((prop(page, "仓库地址").get("url") or ""))
        name = name or textval(prop(page, "仓库名称"))
        if name and "/" in name:
            managed[name.casefold()] = (name, "手动登记", None)
    explicit = {}
    for page in projects:
        for name in links(textval(prop(page, "待关联仓库 URL"))):
            explicit.setdefault(name.casefold(), (name, []))[1].append(page["id"])
            managed.setdefault(name.casefold(), (name, "Notion 项目", None))
    # Discovery is opt-in. No broad import of historical/forked repositories.
    try:
        for repo in paginate_github("/user/repos", {"affiliation": "owner", "visibility": "all", "sort": "updated"}):
            if repo.get("owner", {}).get("login", "").casefold() != OWNER.casefold() or repo.get("fork") or repo.get("archived"):
                continue
            if TOPIC in (repo.get("topics") or []):
                name = repo["full_name"]
                managed.setdefault(name.casefold(), (name, "GitHub Topic", repo))
    except Exception as exc:
        WARNINGS.append(f"Topic discovery unavailable: {exc}")
    return managed, explicit

def main():
    for k in ("GH_PROJECTS_TOKEN", "NOTION_TOKEN"):
        if not os.getenv(k):
            raise RuntimeError("Missing required secret " + k)
    projects = paginate_notion(PROJECTS)
    pages = paginate_notion(REPOS)
    known = {str(prop(p, "GitHub Repo ID").get("rich_text", [{}])[0].get("plain_text", "")): p for p in pages if prop(p, "GitHub Repo ID").get("rich_text")}
    by_url = {name.casefold(): p for p in pages if (name := (url_repo(prop(p, "仓库地址").get("url")) or textval(prop(p, "仓库名称"))))}
    managed, explicit = discover(projects, pages)
    synced, failed = 0, 0
    for key, (name, origin, _metadata) in sorted(managed.items()):
        page = by_url.get(key)
        if page and (prop(page, "管理状态").get("select") or {}).get("name") == "忽略":
            continue
        try:
            repo = github("GET", "/repos/" + urllib.parse.quote(name, safe="/"))
            canonical = repo["full_name"]
            gid = str(repo["id"])
            page = known.get(gid) or page
            branch = textval(prop(page, "跟踪分支")) if page else ""
            branch = branch or repo["default_branch"]
            encoded_branch = urllib.parse.quote(branch, safe="")
            commit = github("GET", f"/repos/{canonical}/commits/{encoded_branch}")
            sha = commit["sha"]
            message = commit["commit"]["message"].splitlines()[0]
            latest_date = commit["commit"]["committer"]["date"]
            prs = paginate_github(f"/repos/{canonical}/pulls", {"state": "open"})
            # Commit-specific check-runs; use combined commit status as fallback if not enabled.
            ci = "未知"
            try:
                checks = github("GET", f"/repos/{canonical}/commits/{sha}/check-runs", params={"per_page": 100}).get("check_runs", [])
                if checks:
                    if any(x.get("status") != "completed" for x in checks):
                        ci = "进行中"
                    elif all(x.get("conclusion") in ("success", "neutral", "skipped") for x in checks):
                        ci = "通过"
                    else:
                        ci = "失败"
                else:
                    status = github("GET", f"/repos/{canonical}/commits/{sha}/status").get("state", "")
                    ci = {"success": "通过", "failure": "失败", "pending": "进行中", "error": "失败"}.get(status, "未知")
            except Exception as exc:
                WARNINGS.append(f"{canonical}: CI unavailable: {exc}")
            related_ids = set(related(page, "关联项目")) if page else set()
            related_ids.update(explicit.get(key, ("", []))[1])
            properties = {
                "仓库名称": title(canonical), "仓库地址": {"url": repo["html_url"]},
                "GitHub Repo ID": rich(gid),
                "可见性": {"select": {"name": repo["visibility"].capitalize()}},
                "默认分支": rich(repo["default_branch"]), "跟踪分支": rich(branch),
                "最后 Push": date(repo.get("pushed_at")),
                "最新分支提交": date(latest_date),
                "最新提交说明": rich(message),
                "最新提交链接": {"url": commit["html_url"]},
                "开放 PR 数": {"number": len(prs)},
                "CI 状态": {"select": {"name": ci}},
                "最后同步时间": date(NOW),
                "同步状态": {"select": {"name": "正常"}},
                "已归档": {"checkbox": bool(repo.get("archived"))},
                "管理状态": {"select": {"name": "管理中" if related_ids else "待关联"}},
            }
            if related_ids:
                properties["关联项目"] = {"relation": [{"id": x} for x in sorted(related_ids)]}
            if page:
                # Avoid rewriting properties that did not change; dates are compared by start time.
                curr = page.get("properties") or {}
                changed = {}
                for k, v in properties.items():
                    old = curr.get(k, {})
                    kind = next(iter(v))
                    oldv = old.get(kind)
                    newv = v[kind]
                    if kind in ("title", "rich_text"):
                        same = textval(old) == textval(v)
                    elif kind == "relation":
                        same = {x["id"] for x in oldv or []} == {x["id"] for x in newv}
                    elif kind == "date":
                        same = (oldv or {}).get("start") == (newv or {}).get("start")
                    else:
                        same = oldv == newv
                    if not same or k == "最后同步时间":
                        changed[k] = v
                update(page["id"], changed)
            else:
                properties["发现来源"] = {"select": {"name": origin}}
                created = create(properties)
                if created:
                    pages.append(created)
            synced += 1
        except Exception as exc:
            failed += 1
            WARNINGS.append(f"{name}: {exc}")
            if page:
                try:
                    update(page["id"], {"同步状态": {"select": {"name": "同步失败"}}})
                except Exception as update_exc:
                    WARNINGS.append(f"Could not mark {name}: {update_exc}")
    # Always re-read counts after any new repo creations.
    try:
        update_dashboard(paginate_notion(PROJECTS), paginate_notion(REPOS))
    except Exception as exc:
        WARNINGS.append(f"Dashboard update failed: {exc}")
    print(json.dumps({"managed": len(managed), "synced": synced, "failed": failed, "dry_run": DRY_RUN, "warnings": WARNINGS}, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
