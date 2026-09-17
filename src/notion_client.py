from __future__ import annotations

import requests


class NotionClient:
    def __init__(self, token: str, data_source_id: str, api_version: str = "2026-03-11") -> None:
        self.data_source_id = data_source_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Notion-Version": api_version,
            "Content-Type": "application/json",
        })

    def query_all(self) -> list[dict]:
        rows: list[dict] = []
        cursor = None
        while True:
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            r = self.session.post(
                f"https://api.notion.com/v1/data_sources/{self.data_source_id}/query",
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            rows.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return rows

    def create_page(self, properties: dict) -> dict:
        r = self.session.post(
            "https://api.notion.com/v1/pages",
            json={
                "parent": {"type": "data_source_id", "data_source_id": self.data_source_id},
                "properties": properties,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def update_page(self, page_id: str, properties: dict) -> None:
        r = self.session.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            json={"properties": properties},
            timeout=30,
        )
        r.raise_for_status()
