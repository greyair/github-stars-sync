from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_rules(path: str = "config/categories.yml") -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def classify_repo(repo: dict, rules: dict) -> str:
    haystack = " ".join([
        repo.get("name", ""),
        repo.get("full_name", ""),
        repo.get("description") or "",
        " ".join(repo.get("topics") or []),
        repo.get("language") or "",
    ]).lower()
    for category, spec in (rules.get("categories") or {}).items():
        for keyword in spec.get("keywords", []):
            if str(keyword).lower() in haystack:
                return category
    return rules.get("default", "稍后研究")


def activity_status(repo: dict) -> str:
    if repo.get("archived"):
        return "已归档"
    pushed_at = repo.get("pushed_at")
    if not pushed_at:
        return "长期未更新"
    pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    days = (datetime.now(timezone.utc) - pushed).days
    if days <= 180:
        return "活跃"
    if days <= 365:
        return "近期活跃"
    if days <= 730:
        return "较久未更新"
    return "长期未更新"
