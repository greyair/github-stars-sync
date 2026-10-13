"""Offline contract tests for project dashboard synchronization."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import project_dashboard_sync as sync


def callout(label, number, caption, index):
    return {
        "id": f"callout-{index}", "type": "callout", "has_children": True,
        "callout": {"rich_text": [{"plain_text": label}]},
        "_children": [
            {"id": f"heading-{index}", "type": "heading_1",
             "heading_1": {"rich_text": [{"plain_text": number}]}},
            {"id": f"caption-{index}", "type": "paragraph",
             "paragraph": {"rich_text": [{"plain_text": caption,
                                        "annotations": {"color": "green"}}]}},
        ],
    }


class DashboardSyncTests(unittest.TestCase):
    def test_valid_repo_urls(self):
        self.assertEqual(sync.url_repo("https://github.com/greyair/NotlistGPT.git"),
                         "greyair/NotlistGPT")
        self.assertEqual(sync.url_repo("https://github.com/greyair/GameBridge/"),
                         "greyair/GameBridge")
        self.assertIsNone(sync.url_repo("https://evil.example.com/greyair/Example"))
        self.assertEqual(sync.links("https://github.com/a/one, https://github.com/b/two"),
                         ["a/one", "b/two"])

    def test_stats_and_priorities(self):
        def project(priority):
            return {"properties": {"执行优先级": {"select":
                    {"name": priority} if priority else None}}}
        stats, counts = sync.dashboard_stats(
            [project("P0"), project("P1"), project(None)], [{}, {}])
        self.assertEqual(stats, {"项目总数": 3, "仓库总数": 2, "已分级项目": 2})
        self.assertEqual(counts, {"P0": 1, "P1": 1, "P2": 0, "P3": 0})

    def test_discovery_opt_in_and_preserves_existing(self):
        pages = [{
            "id": "existing", "properties": {
                "仓库名称": {"title": [{"plain_text": "greyair/current"}]},
                "仓库地址": {"url": "https://github.com/greyair/current"},
            }
        }]
        projects = [{
            "id": "project-new", "properties": {
                "待关联仓库 URL": {"rich_text": [
                    {"plain_text": "https://github.com/greyair/new"}]}
            }
        }]
        repo = {"full_name": "greyair/topic", "topics": ["notion-managed"],
                "owner": {"login": "greyair"}, "fork": False, "archived": False}
        with patch.object(sync, "paginate_github", return_value=[repo]):
            managed, explicit = sync.discover(projects, pages)
        self.assertEqual(set(managed), {
            "greyair/current", "greyair/new", "greyair/topic"})
        self.assertEqual(explicit["greyair/new"][1], ["project-new"])

    def test_updating_three_cards_and_captions(self):
        card_list = [
            callout("项目总数", "10", "已登记 10 个项目", 1),
            callout("仓库总数", "9", "已登记 9 个仓库", 2),
            callout("已分级项目", "10", "P0 1 · P1 2 · P2 3 · P3 4", 3),
        ]
        layout = {
            sync.HOME: [{"id": "outer", "type": "column_list", "has_children": True}],
            "outer": [{"id": "column", "type": "column", "has_children": True}],
            "column": card_list,
        }
        layout.update({card["id"]: card["_children"] for card in card_list})
        projects = [
            {"properties": {"执行优先级": {"select": {"name": "P0"}}}},
            {"properties": {"执行优先级": {"select": {"name": "P1"}}}},
            {"properties": {"执行优先级": {"select": None}}},
        ]
        logs = []
        with patch.object(sync, "blocks", side_effect=lambda bid: layout.get(bid, [])):
            with patch.object(sync, "notion", side_effect=lambda *a, **kw: logs.append((a, kw))):
                with patch.object(sync, "DRY_RUN", False):
                    with patch.object(sync, "WARNINGS", []):
                        sync.update_dashboard(projects, [{}, {}])
        self.assertEqual(len(logs), 6)
        self.assertTrue(any(args[1] == "/blocks/heading-1" for args, _ in logs))
        self.assertTrue(any(args[1] == "/blocks/caption-1" for args, _ in logs))
        self.assertTrue(any(args[1] == "/blocks/caption-3" for args, _ in logs))

    def test_checks_permission_falls_back_to_commit_statuses(self):
        fallback = [{"state": "success", "statuses": [{"state": "success"}]}]
        with patch.object(sync, "github", side_effect=[RuntimeError("HTTP 403: Checks"), *fallback]):
            with patch.object(sync, "WARNINGS", []) as warnings:
                self.assertEqual(sync.read_ci("greyair/example", "deadbeef"), "通过")
                self.assertEqual(len(warnings), 1)

    def test_missing_stat_card_fails(self):
        with patch.object(sync, "blocks", return_value=[]):
            with patch.object(sync, "WARNINGS", []):
                with self.assertRaisesRegex(RuntimeError, "Dashboard cards"):
                    sync.update_dashboard([], [])


if __name__ == "__main__":
    unittest.main()
