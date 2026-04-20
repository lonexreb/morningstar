"""Tests for the 24/7 queue processor in engine.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from morningstar.engine import (
    PendingItem,
    QueueConfig,
    TaskResult,
    _iso_week_key,
    fetch_pending_jira,
    fetch_pending_notion,
    process_queue,
    read_weekly_spend,
    set_jira_status,
    set_notion_status,
    validate_gh_repo,
    validate_jira_project_key,
    validate_jira_url,
    validate_notion_db_id,
    validate_notion_token,
    write_weekly_spend,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def _cfg(tmp_repo: Path, **overrides) -> QueueConfig:
    base = {
        "repo_path": tmp_repo,
        "notion_db_id": "11111111111111111111111111111111",
        "notion_token": "secret_" + "x" * 40,
        "jira_url": "",
        "jira_email": "",
        "jira_token": "",
        "jira_project_key": "",
        "slack_webhook": "",
        "per_run_budget": 10.0,
        "weekly_budget": 100.0,
    }
    base.update(overrides)
    return QueueConfig(**base)


# ── Validators ────────────────────────────────────────────────


class TestValidators:
    def test_notion_db_id_accepts_32_hex(self) -> None:
        validate_notion_db_id("a" * 32)

    def test_notion_db_id_accepts_dashed(self) -> None:
        validate_notion_db_id("12345678-1234-1234-1234-123456789abc")

    def test_notion_db_id_rejects_short(self) -> None:
        with pytest.raises(ValueError):
            validate_notion_db_id("short")

    def test_notion_token_accepts_secret_prefix(self) -> None:
        validate_notion_token("secret_" + "a" * 40)

    def test_notion_token_accepts_ntn_prefix(self) -> None:
        validate_notion_token("ntn_" + "a" * 40)

    def test_notion_token_rejects_plain(self) -> None:
        with pytest.raises(ValueError):
            validate_notion_token("plain_token")

    def test_jira_url_trims_trailing_slash(self) -> None:
        assert validate_jira_url("https://x.atlassian.net/") == "https://x.atlassian.net"

    def test_jira_url_rejects_path(self) -> None:
        with pytest.raises(ValueError):
            validate_jira_url("https://x.atlassian.net/browse/ABC")

    def test_jira_project_key_accepts_upper(self) -> None:
        validate_jira_project_key("ABC")

    def test_jira_project_key_rejects_lower(self) -> None:
        with pytest.raises(ValueError):
            validate_jira_project_key("abc")

    def test_gh_repo_accepts_owner_name(self) -> None:
        validate_gh_repo("owner/name")

    def test_gh_repo_rejects_url(self) -> None:
        with pytest.raises(ValueError):
            validate_gh_repo("https://github.com/owner/name")


# ── Notion API ────────────────────────────────────────────────


class TestFetchPendingNotion:
    @patch("morningstar.engine.httpx.post")
    def test_returns_pending_items(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "results": [
                    {
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Build auth"}],
                            },
                        },
                    },
                    {
                        "id": "page-2",
                        "url": "https://notion.so/page-2",
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Add dashboard"}],
                            },
                            "PRD URL": {
                                "type": "url",
                                "url": "https://notion.so/spec-42",
                            },
                        },
                    },
                ]
            },
        )
        mock_post.return_value.raise_for_status = lambda: None

        items = fetch_pending_notion("a" * 32, "secret_" + "x" * 40)
        assert len(items) == 2
        assert items[0].source == "notion"
        assert items[0].title == "Build auth"
        assert items[0].prd_url == "https://notion.so/page-1"
        assert items[1].prd_url == "https://notion.so/spec-42"  # override wins

    @patch("morningstar.engine.httpx.post")
    def test_handles_http_error(self, mock_post: MagicMock) -> None:
        import httpx
        mock_post.side_effect = httpx.HTTPError("boom")
        items = fetch_pending_notion("a" * 32, "secret_" + "x" * 40)
        assert items == []


class TestSetNotionStatus:
    @patch("morningstar.engine.httpx.patch")
    def test_sets_status_select(self, mock_patch: MagicMock) -> None:
        mock_patch.return_value = MagicMock(status_code=200)
        mock_patch.return_value.raise_for_status = lambda: None

        ok = set_notion_status("page-1", "secret_" + "x" * 40, "Done", pr_url="https://gh/pr/1")
        assert ok is True
        body = mock_patch.call_args.kwargs["json"]
        assert body["properties"]["Status"]["select"]["name"] == "Done"
        assert body["properties"]["PR"]["url"] == "https://gh/pr/1"


# ── Jira API ──────────────────────────────────────────────────


class TestFetchPendingJira:
    @patch("morningstar.engine.httpx.get")
    def test_extracts_notion_url_from_description(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(
            json=lambda: {
                "issues": [
                    {
                        "key": "ABC-42",
                        "fields": {
                            "summary": "Fix login",
                            "description": "See the spec at https://notion.so/login-spec-abc",
                        },
                    },
                ]
            }
        )
        mock_get.return_value.raise_for_status = lambda: None

        items = fetch_pending_jira(
            "https://x.atlassian.net", "ABC",
            "me@x.com", "token",
        )
        assert len(items) == 1
        assert items[0].source == "jira"
        assert items[0].source_id == "ABC-42"
        assert items[0].prd_url == "https://notion.so/login-spec-abc"

    @patch("morningstar.engine.httpx.get")
    def test_falls_back_to_inline_description(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(
            json=lambda: {
                "issues": [
                    {
                        "key": "ABC-99",
                        "fields": {
                            "summary": "Add feature",
                            "description": "No URL here, just a written PRD body.",
                        },
                    },
                ]
            }
        )
        mock_get.return_value.raise_for_status = lambda: None

        items = fetch_pending_jira(
            "https://x.atlassian.net", "ABC",
            "me@x.com", "token",
        )
        assert items[0].prd_url == ""
        assert "No URL here" in items[0].inline_prd_text


class TestSetJiraStatus:
    @patch("morningstar.engine.httpx.post")
    @patch("morningstar.engine.httpx.get")
    def test_finds_transition_by_name(
        self, mock_get: MagicMock, mock_post: MagicMock,
    ) -> None:
        mock_get.return_value = MagicMock(
            json=lambda: {
                "transitions": [
                    {"id": "31", "name": "In Progress"},
                    {"id": "41", "name": "Done"},
                ]
            },
        )
        mock_get.return_value.raise_for_status = lambda: None
        mock_post.return_value = MagicMock(status_code=204)
        mock_post.return_value.raise_for_status = lambda: None

        ok = set_jira_status(
            "https://x.atlassian.net", "ABC-1",
            "me@x.com", "token", "Done",
        )
        assert ok is True
        assert mock_post.call_args.kwargs["json"]["transition"]["id"] == "41"


# ── Weekly budget ─────────────────────────────────────────────


class TestWeeklyBudget:
    def test_round_trip(self, tmp_repo: Path) -> None:
        key, spend = read_weekly_spend(tmp_repo)
        assert spend == 0.0
        write_weekly_spend(tmp_repo, key, 12.5)
        key2, spend2 = read_weekly_spend(tmp_repo)
        assert key2 == key
        assert spend2 == 12.5

    def test_new_week_resets(self, tmp_repo: Path) -> None:
        write_weekly_spend(tmp_repo, "1999-W01", 99.0)
        _, spend = read_weekly_spend(tmp_repo)
        assert spend == 0.0

    def test_iso_key_format(self) -> None:
        key = _iso_week_key()
        assert len(key) == 8 and key[4] == "-" and key[5] == "W"


# ── process_queue end-to-end (mocked) ─────────────────────────


class TestProcessQueue:
    @patch("morningstar.engine.fetch_pending_notion")
    @patch("morningstar.engine.fetch_pending_jira")
    def test_empty_queue_returns_zero(
        self, mock_jira: MagicMock, mock_notion: MagicMock,
        tmp_repo: Path,
    ) -> None:
        mock_notion.return_value = []
        mock_jira.return_value = []
        result = process_queue(_cfg(tmp_repo))
        assert result.scanned == 0
        assert result.processed == 0

    @patch("morningstar.engine.fetch_pending_notion")
    def test_dry_run_skips(
        self, mock_notion: MagicMock, tmp_repo: Path,
    ) -> None:
        mock_notion.return_value = [
            PendingItem(source="notion", source_id="p1", title="Work",
                        prd_url="https://notion.so/p1"),
        ]
        result = process_queue(_cfg(tmp_repo, dry_run=True))
        assert result.scanned == 1
        assert result.skipped == 1
        assert result.processed == 0

    @patch("morningstar.engine.open_github_pr")
    @patch("morningstar.engine.execute_task")
    @patch("morningstar.engine.generate_tasks")
    @patch("morningstar.engine.fetch_prd")
    @patch("morningstar.engine._prepare_branch")
    @patch("morningstar.engine.set_notion_status")
    @patch("morningstar.engine.fetch_pending_notion")
    def test_happy_path_marks_done(
        self,
        mock_notion: MagicMock,
        mock_set_status: MagicMock,
        mock_branch: MagicMock,
        mock_fetch_prd: MagicMock,
        mock_gen: MagicMock,
        mock_exec: MagicMock,
        mock_pr: MagicMock,
        tmp_repo: Path,
    ) -> None:
        mock_notion.return_value = [
            PendingItem(source="notion", source_id="page-1", title="Feature X",
                        prd_url="https://notion.so/page-1"),
        ]
        mock_branch.return_value = True
        mock_fetch_prd.return_value = ("PRD body", 0.5)
        mock_gen.return_value = (
            [{"id": "t1", "title": "Do X", "description": "d"}],
            0.3,
        )
        mock_exec.return_value = TaskResult(
            task_id="t1", title="Do X", success=True, cost=1.2,
        )
        mock_pr.return_value = "https://github.com/owner/repo/pull/1"
        mock_set_status.return_value = True

        result = process_queue(_cfg(tmp_repo))
        assert result.succeeded == 1
        assert result.failed == 0
        assert result.prs_opened == ["https://github.com/owner/repo/pull/1"]
        assert any(
            call.args[2] == "Done" for call in mock_set_status.call_args_list
        )
        assert any(
            call.args[2] == "Running" for call in mock_set_status.call_args_list
        )

    @patch("morningstar.engine.fetch_pending_notion")
    def test_weekly_budget_exhausted_short_circuits(
        self, mock_notion: MagicMock, tmp_repo: Path,
    ) -> None:
        mock_notion.return_value = [
            PendingItem(source="notion", source_id="p1", title="x",
                        prd_url="https://notion.so/p1"),
        ]
        write_weekly_spend(tmp_repo, _iso_week_key(), 999.0)
        result = process_queue(_cfg(tmp_repo, weekly_budget=100.0))
        assert result.processed == 0

    @patch("morningstar.engine.open_github_pr")
    @patch("morningstar.engine.execute_task")
    @patch("morningstar.engine.generate_tasks")
    @patch("morningstar.engine.fetch_prd")
    @patch("morningstar.engine._prepare_branch")
    @patch("morningstar.engine.set_notion_status")
    @patch("morningstar.engine.fetch_pending_notion")
    def test_task_failure_marks_failed(
        self,
        mock_notion: MagicMock,
        mock_set_status: MagicMock,
        mock_branch: MagicMock,
        mock_fetch_prd: MagicMock,
        mock_gen: MagicMock,
        mock_exec: MagicMock,
        mock_pr: MagicMock,
        tmp_repo: Path,
    ) -> None:
        mock_notion.return_value = [
            PendingItem(source="notion", source_id="page-1", title="Bad",
                        prd_url="https://notion.so/page-1"),
        ]
        mock_branch.return_value = True
        mock_fetch_prd.return_value = ("PRD body", 0.5)
        mock_gen.return_value = (
            [{"id": "t1", "title": "Do X", "description": "d"}],
            0.3,
        )
        mock_exec.return_value = TaskResult(
            task_id="t1", title="Do X", success=False, cost=1.2,
        )
        mock_pr.return_value = None
        mock_set_status.return_value = True

        result = process_queue(_cfg(tmp_repo))
        assert result.failed == 1
        assert result.succeeded == 0
        assert any(
            call.args[2] == "Failed" for call in mock_set_status.call_args_list
        )

    @patch("morningstar.engine.fetch_pending_jira")
    @patch("morningstar.engine.fetch_pending_notion")
    def test_both_sources_aggregated(
        self,
        mock_notion: MagicMock,
        mock_jira: MagicMock,
        tmp_repo: Path,
    ) -> None:
        mock_notion.return_value = [
            PendingItem(source="notion", source_id="n1", title="N-work",
                        prd_url="https://notion.so/n1"),
        ]
        mock_jira.return_value = [
            PendingItem(source="jira", source_id="ABC-5", title="J-work",
                        prd_url="https://notion.so/spec"),
        ]
        cfg = _cfg(
            tmp_repo,
            jira_url="https://x.atlassian.net",
            jira_email="me@x.com",
            jira_token="t",
            jira_project_key="ABC",
            dry_run=True,
        )
        result = process_queue(cfg)
        assert result.scanned == 2
        assert result.skipped == 2


class TestPrepareBranch:
    @patch("morningstar.engine.subprocess.run")
    def test_checkout_success(self, mock_run: MagicMock, tmp_repo: Path) -> None:
        from morningstar.engine import _prepare_branch
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="",
        )
        assert _prepare_branch(tmp_repo, "morningstar/foo") is True

    @patch("morningstar.engine.subprocess.run")
    def test_checkout_failure(self, mock_run: MagicMock, tmp_repo: Path) -> None:
        from morningstar.engine import _prepare_branch
        mock_run.side_effect = subprocess.CalledProcessError(1, [], stderr="boom")
        assert _prepare_branch(tmp_repo, "morningstar/foo") is False


class TestOpenGithubPR:
    @patch("morningstar.engine.subprocess.run")
    def test_returns_pr_url(self, mock_run: MagicMock, tmp_repo: Path) -> None:
        from morningstar.engine import open_github_pr
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="https://github.com/owner/repo/pull/42\n", stderr="",
            ),
        ]
        url = open_github_pr(tmp_repo, "feat/x", "title", "body")
        assert url == "https://github.com/owner/repo/pull/42"


class TestPendingItemExtraction:
    def test_pending_item_is_frozen(self) -> None:
        item = PendingItem(source="notion", source_id="p1", title="x")
        with pytest.raises(Exception):
            item.source = "jira"  # type: ignore[misc]


def test_import_ok() -> None:
    """Regression -- make sure the module imports cleanly after additions."""
    from morningstar.engine import process_queue as pq
    assert callable(pq)


def test_json_round_trip() -> None:
    """Weekly-spend JSON is stable format."""
    data = {"week": "2026-W15", "spend": 12.5}
    assert json.loads(json.dumps(data)) == data
