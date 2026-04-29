"""Tests for run history persistence and the `morningstar status` command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from morningstar.cli import app
from morningstar.engine import _RUN_HISTORY_MAX as RUN_HISTORY_MAX
from morningstar.engine import (
    PendingItem,
    QueueConfig,
    RunRecord,
    _run_history_path,
    append_run_history,
    process_queue,
    read_run_history,
)

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def _record(**overrides: object) -> RunRecord:
    base = {
        "timestamp": "2026-04-29T16:00:00+00:00",
        "week_key": "2026-W18",
        "scanned": 1,
        "processed": 1,
        "succeeded": 1,
        "failed": 0,
        "skipped": 0,
        "total_cost": 0.5,
        "weekly_spend_after": 1.5,
        "weekly_budget": 200.0,
        "prs_opened": ("https://github.com/o/r/pull/1",),
        "dry_run": False,
    }
    base.update(overrides)
    return RunRecord(**base)  # type: ignore[arg-type]


# ── RunRecord ─────────────────────────────────────────────────


class TestRunRecord:
    def test_frozen(self) -> None:
        rec = _record()
        with pytest.raises(Exception):  # FrozenInstanceError
            rec.scanned = 99  # type: ignore[misc]

    def test_round_trip_serialization(self) -> None:
        original = _record()
        recovered = RunRecord.from_dict(
            __import__("json").loads(original.to_json())
        )
        assert recovered == original

    def test_from_dict_handles_missing_fields(self) -> None:
        rec = RunRecord.from_dict({})
        assert rec.scanned == 0
        assert rec.prs_opened == ()
        assert rec.dry_run is False

    def test_from_dict_coerces_types(self) -> None:
        rec = RunRecord.from_dict({
            "scanned": "5",  # string -> int
            "total_cost": "1.5",  # string -> float
            "prs_opened": ["a", "b"],  # list -> tuple
            "dry_run": 1,  # int -> bool
        })
        assert rec.scanned == 5
        assert rec.total_cost == 1.5
        assert rec.prs_opened == ("a", "b")
        assert rec.dry_run is True


# ── History append / read ─────────────────────────────────────


class TestHistoryFile:
    def test_append_and_read(self, tmp_repo: Path) -> None:
        append_run_history(tmp_repo, _record(scanned=1))
        append_run_history(tmp_repo, _record(scanned=2))
        recs = read_run_history(tmp_repo)
        assert len(recs) == 2
        assert [r.scanned for r in recs] == [1, 2]

    def test_read_empty(self, tmp_repo: Path) -> None:
        assert read_run_history(tmp_repo) == []

    def test_limit_keeps_most_recent(self, tmp_repo: Path) -> None:
        for i in range(5):
            append_run_history(tmp_repo, _record(scanned=i))
        recs = read_run_history(tmp_repo, limit=2)
        assert [r.scanned for r in recs] == [3, 4]

    def test_corrupt_lines_skipped(self, tmp_repo: Path) -> None:
        path = _run_history_path(tmp_repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _record(scanned=1).to_json() + "\n"
            + "not valid json\n"
            + _record(scanned=2).to_json() + "\n"
        )
        recs = read_run_history(tmp_repo)
        assert [r.scanned for r in recs] == [1, 2]

    def test_history_trimmed_at_max(self, tmp_repo: Path) -> None:
        # Write more than the cap and ensure we keep only the most recent.
        for i in range(RUN_HISTORY_MAX + 10):
            append_run_history(tmp_repo, _record(scanned=i))
        recs = read_run_history(tmp_repo)
        assert len(recs) == RUN_HISTORY_MAX
        # First kept record should be the (10)th appended (0..9 trimmed off).
        assert recs[0].scanned == 10
        assert recs[-1].scanned == RUN_HISTORY_MAX + 9

    def test_creates_morningstar_dir(self, tmp_repo: Path) -> None:
        append_run_history(tmp_repo, _record())
        assert (tmp_repo / ".morningstar" / "run-history.jsonl").exists()


# ── process_queue persists history ────────────────────────────


def _cfg(tmp_repo: Path, **overrides: object) -> QueueConfig:
    base = {
        "repo_path": tmp_repo,
        "notion_db_id": "11111111111111111111111111111111",
        "notion_token": "secret_" + "x" * 40,
        "weekly_budget": 100.0,
    }
    base.update(overrides)
    return QueueConfig(**base)  # type: ignore[arg-type]


class TestProcessQueueWritesHistory:
    @patch("morningstar.engine.fetch_pending_notion")
    def test_no_pending_writes_record(
        self, mock_notion: MagicMock, tmp_repo: Path
    ) -> None:
        mock_notion.return_value = []
        process_queue(_cfg(tmp_repo))
        recs = read_run_history(tmp_repo)
        assert len(recs) == 1
        assert recs[0].scanned == 0
        assert recs[0].processed == 0

    @patch("morningstar.engine.fetch_pending_notion")
    def test_weekly_budget_exhausted_writes_record(
        self, mock_notion: MagicMock, tmp_repo: Path
    ) -> None:
        from morningstar.engine import _iso_week_key, write_weekly_spend
        mock_notion.return_value = [
            PendingItem(source="notion", source_id="p1", title="x",
                        prd_url="https://notion.so/p1"),
        ]
        write_weekly_spend(tmp_repo, _iso_week_key(), 999.0)
        process_queue(_cfg(tmp_repo, weekly_budget=100.0))
        recs = read_run_history(tmp_repo)
        assert len(recs) == 1
        assert recs[0].scanned == 1
        assert recs[0].processed == 0
        assert recs[0].weekly_spend_after >= 999.0

    @patch("morningstar.engine.fetch_pending_notion")
    def test_dry_run_recorded(
        self, mock_notion: MagicMock, tmp_repo: Path
    ) -> None:
        mock_notion.return_value = [
            PendingItem(source="notion", source_id="p1", title="x",
                        prd_url="https://notion.so/p1"),
        ]
        process_queue(_cfg(tmp_repo, dry_run=True))
        recs = read_run_history(tmp_repo)
        assert len(recs) == 1
        assert recs[0].dry_run is True
        assert recs[0].skipped == 1


# ── status CLI ────────────────────────────────────────────────


class TestStatusCommand:
    def test_status_empty_history(self, tmp_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["status", "--repo", str(tmp_repo)])
        assert result.exit_code == 0
        assert "No run history yet" in result.stdout

    def test_status_renders_history(self, tmp_repo: Path) -> None:
        append_run_history(
            tmp_repo,
            _record(scanned=3, succeeded=2, failed=1, total_cost=4.25,
                    weekly_spend_after=12.5),
        )
        append_run_history(
            tmp_repo,
            _record(scanned=1, succeeded=1, failed=0, total_cost=0.75,
                    weekly_spend_after=13.25),
        )
        runner = CliRunner()
        result = runner.invoke(app, ["status", "--repo", str(tmp_repo)])
        assert result.exit_code == 0
        # Spend bar shows the latest weekly_spend_after's dollars.
        # Recent runs table shows both entries' costs.
        assert "$4.25" in result.stdout
        assert "$0.75" in result.stdout
        # PRs should appear
        assert "github.com/o/r/pull/1" in result.stdout

    def test_status_respects_limit(self, tmp_repo: Path) -> None:
        for i in range(5):
            append_run_history(tmp_repo, _record(scanned=i, total_cost=i + 1.0))
        runner = CliRunner()
        result = runner.invoke(
            app, ["status", "--repo", str(tmp_repo), "--limit", "2"]
        )
        assert result.exit_code == 0
        # Only the last 2 cost values should be present
        assert "$5.00" in result.stdout
        assert "$4.00" in result.stdout
        # Earlier ones should NOT appear in recent-runs table
        assert "$1.00" not in result.stdout

    def test_status_health_summary_high_failure(self, tmp_repo: Path) -> None:
        for _ in range(5):
            append_run_history(
                tmp_repo,
                _record(scanned=1, processed=1, succeeded=0, failed=1),
            )
        runner = CliRunner()
        result = runner.invoke(app, ["status", "--repo", str(tmp_repo)])
        assert result.exit_code == 0
        assert "0.0%" in result.stdout  # success rate


# ── --json output ─────────────────────────────────────────────


class TestStatusJson:
    def test_json_empty_history(self, tmp_repo: Path) -> None:
        import json as _json
        runner = CliRunner()
        result = runner.invoke(
            app, ["status", "--repo", str(tmp_repo), "--json"]
        )
        assert result.exit_code == 0
        payload = _json.loads(result.stdout)
        assert payload["runs"] == []
        assert payload["window"]["runs"] == 0
        assert payload["weekly_spend"] == 0.0
        assert payload["recent_prs"] == []

    def test_json_includes_aggregate_metrics(self, tmp_repo: Path) -> None:
        import json as _json
        append_run_history(
            tmp_repo,
            _record(scanned=2, processed=2, succeeded=1, failed=1, total_cost=3.0),
        )
        append_run_history(
            tmp_repo,
            _record(scanned=1, processed=1, succeeded=1, failed=0, total_cost=2.0),
        )
        runner = CliRunner()
        result = runner.invoke(
            app, ["status", "--repo", str(tmp_repo), "--json"]
        )
        assert result.exit_code == 0
        payload = _json.loads(result.stdout)
        assert payload["window"]["runs"] == 2
        assert payload["window"]["items_processed"] == 3
        assert payload["window"]["items_succeeded"] == 2
        assert payload["window"]["items_failed"] == 1
        assert payload["window"]["total_cost"] == 5.0
        assert payload["window"]["success_rate_pct"] == pytest.approx(66.67, rel=1e-2)
        assert len(payload["runs"]) == 2

    def test_json_no_banner_emitted(self, tmp_repo: Path) -> None:
        """--json must keep stdout pristine (jq-pipeable)."""
        import json as _json
        append_run_history(tmp_repo, _record())
        runner = CliRunner()
        result = runner.invoke(
            app, ["status", "--repo", str(tmp_repo), "--json"]
        )
        assert result.exit_code == 0
        # Whole stdout should parse as JSON -- no leading banner allowed.
        _json.loads(result.stdout)


# ── --since filter ───────────────────────────────────────────


class TestStatusSince:
    def test_parse_duration_units(self) -> None:
        from datetime import timedelta

        from morningstar.cli import _parse_duration
        assert _parse_duration("30s") == timedelta(seconds=30)
        assert _parse_duration("10m") == timedelta(minutes=10)
        assert _parse_duration("24h") == timedelta(hours=24)
        assert _parse_duration("7d") == timedelta(days=7)
        assert _parse_duration("24H") == timedelta(hours=24)  # case-insensitive

    def test_parse_duration_rejects_garbage(self) -> None:
        from morningstar.cli import _parse_duration
        for bad in ["", "abc", "1y", "-3h", "3hr", "1.5h"]:
            with pytest.raises(ValueError):
                _parse_duration(bad)

    def test_since_filters_old_records(self, tmp_repo: Path) -> None:
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        old = (now - _dt.timedelta(days=30)).isoformat(timespec="seconds")
        recent = (now - _dt.timedelta(hours=1)).isoformat(timespec="seconds")
        append_run_history(tmp_repo, _record(timestamp=old, scanned=99))
        append_run_history(tmp_repo, _record(timestamp=recent, scanned=11))

        import json as _json
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["status", "--repo", str(tmp_repo), "--since", "24h", "--json"],
        )
        assert result.exit_code == 0
        payload = _json.loads(result.stdout)
        assert len(payload["runs"]) == 1
        assert payload["runs"][0]["scanned"] == 11

    def test_since_invalid_duration_exits_nonzero(self, tmp_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app, ["status", "--repo", str(tmp_repo), "--since", "bogus"]
        )
        assert result.exit_code != 0

    def test_since_empty_window_message(self, tmp_repo: Path) -> None:
        import datetime as _dt
        old = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)
        ).isoformat(timespec="seconds")
        append_run_history(tmp_repo, _record(timestamp=old))
        runner = CliRunner()
        result = runner.invoke(
            app, ["status", "--repo", str(tmp_repo), "--since", "1h"]
        )
        assert result.exit_code == 0
        assert "No runs in the last 1h" in result.stdout
