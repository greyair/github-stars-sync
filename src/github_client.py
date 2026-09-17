from __future__ import annotations

import requests


class GitHubClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.star+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def list_starred(self) -> list[dict]:
        items: list[dict] = []
        page = 1
        while True:
            r = self.session.get(f"{self.api_url}/user/starred", params={"per_page": 100, "page": page}, timeout=30)
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return items

    def star(self, full_name: str) -> None:
        r = self.session.put(f"{self.api_url}/user/starred/{full_name}", timeout=30)
        r.raise_for_status()

    def unstar(self, full_name: str) -> None:
        r = self.session.delete(f"{self.api_url}/user/starred/{full_name}", timeout=30)
        r.raise_for_status()
