from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from classify import activity_status, classify_repo, load_rules
from github_client import GitHubClient
from notion_client import NotionClient


def rich_text(value: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]}


def title(value: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": value[:2000]}}]}


def select(value: str | None) -> dict:
    return {"select": {"name": value}} if value else {"select": None}


def checkbox(value: bool) -> dict:
    return {"checkbox": bool(value)}


def number(value: int | float) -> dict:
    return {"number": value}


def url(value: str) -> dict:
    return {"url": value}


def date(value: str | None) -> dict:
    return {"date": {"start": value}} if value else {"date": None}


def prop_text(page: dict, name: str) -> str:
    prop = (page.get("properties") or {}).get(name) or {}
    items = prop.get("title") or prop.get("rich_text") or []
    return "".join(x.get("plain_text", "") for x in items)


def prop_select(page: dict, name: str) -> str | None:
    prop = (page.get("properties") or {}).get(name) or {}
    item = prop.get("select")
    return item.get("name") if item else None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_properties(repo: dict, starred_at: str | None, category: str, existing_list: str | None) -> dict:
    full_name = repo["full_name"]
    return {
        "Repository": title(full_name),
        "URL": url(repo["html_url"]),
        "Owner": rich_text(repo["owner"]["login"]),
        "描述": rich_text(repo.get("description") or ""),
        "语言": rich_text(repo.get("language") or ""),
        "Topics": rich_text(", ".join(repo.get("topics") or [])),
        "Stars": number(repo.get("stargazers_count", 0)),
        "Forks": number(repo.get("forks_count", 0)),
        "Archived": checkbox(repo.get("archived", False)),
        "最后 Push": date(repo.get("pushed_at")),
        "Starred At": date(starred_at),
        "活跃度": select(activity_status(repo)),
        "List": select(existing_list or category),
        "当前 Star": checkbox(True),
        "最后同步时间": date(now_iso()),
        "同步操作": select("无"),
    }


def main() -> None:
    load_dotenv()
    gh_token = os.environ["GH_STARS_TOKEN"]
    notion_token = os.environ["NOTION_TOKEN"]
    data_source_id = os.environ["NOTION_DATA_SOURCE_ID"]
    gh = GitHubClient(gh_token, os.getenv("GITHUB_API_URL", "https://api.github.com"))
    notion = NotionClient(notion_token, data_source_id, os.getenv("NOTION_API_VERSION", "2026-03-11"))
    rules = load_rules()

    pages = notion.query_all()
    by_repo = {prop_text(p, "Repository"): p for p in pages if prop_text(p, "Repository")}

    # Notion -> GitHub commands first.
    for full_name, page in by_repo.items():
        action = prop_select(page, "同步操作")
        if action == "Star":
            gh.star(full_name)
        elif action == "Unstar":
            gh.unstar(full_name)

    # GitHub is then re-read as the source of truth.
    starred_items = gh.list_starred()
    current: dict[str, dict] = {}
    for item in starred_items:
        repo = item.get("repo", item)
        current[repo["full_name"]] = {"repo": repo, "starred_at": item.get("starred_at")}

    for full_name, item in current.items():
        repo = item["repo"]
        existing = by_repo.get(full_name)
        existing_list = prop_select(existing, "List") if existing else None
        props = repo_properties(repo, item.get("starred_at"), classify_repo(repo, rules), existing_list)
        if existing:
            notion.update_page(existing["id"], props)
        else:
            props["建议"] = select("待定")
            props["已复核"] = checkbox(False)
            notion.create_page(props)

    # Keep history, but mark repositories no longer starred.
    for full_name, page in by_repo.items():
        if full_name not in current:
            notion.update_page(page["id"], {
                "当前 Star": checkbox(False),
                "最后同步时间": date(now_iso()),
                "同步操作": select("无"),
            })

    print(f"Synced {len(current)} current stars; Notion contains {len(by_repo)} existing records before this run.")


if __name__ == "__main__":
    main()
