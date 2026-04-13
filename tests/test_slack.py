"""Tests for two-way Slack communication."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from morningstar.engine import (
    parse_question_block,
    slack_post_and_get_reply,
    validate_bot_token,
)


# ── validate_bot_token ────────────────────────────────────────


class TestValidateBotToken:
    def test_accepts_valid_token(self) -> None:
        assert validate_bot_token("xoxb-123-456-abc") == "xoxb-123-456-abc"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="xoxb-"):
            validate_bot_token("")

    def test_rejects_user_token(self) -> None:
        with pytest.raises(ValueError):
            validate_bot_token("xoxp-user-token-here")

    def test_rejects_random_string(self) -> None:
        with pytest.raises(ValueError):
            validate_bot_token("not-a-token")

    def test_rejects_webhook_url(self) -> None:
        with pytest.raises(ValueError):
            validate_bot_token("https://hooks.slack.com/services/T1/B2/abc")


# ── parse_question_block ─────────────────────────────────────


class TestParseQuestionBlock:
    def test_parses_full_block(self) -> None:
        text = (
            "I've implemented the feature but need clarification.\n"
            "QUESTION: Should the API return paginated results?\n"
            "CONTEXT: The endpoint could return hundreds of records.\n"
            "DEFAULT: I'll add pagination with limit=50."
        )
        result = parse_question_block(text)
        assert result is not None
        question, context, default = result
        assert "paginated" in question
        assert "hundreds" in context
        assert "limit=50" in default

    def test_parses_question_only(self) -> None:
        text = "Some output\nQUESTION: Which database should I use?"
        result = parse_question_block(text)
        assert result is not None
        question, context, default = result
        assert "database" in question
        assert context == ""
        assert default == ""

    def test_returns_none_when_no_question(self) -> None:
        text = "Everything went fine. Task completed successfully."
        assert parse_question_block(text) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert parse_question_block("") is None

    def test_parses_question_with_context_no_default(self) -> None:
        text = (
            "QUESTION: Use REST or GraphQL?\n"
            "CONTEXT: Both are supported by the framework."
        )
        result = parse_question_block(text)
        assert result is not None
        question, context, default = result
        assert "REST" in question
        assert "framework" in context
        assert default == ""

    def test_handles_surrounding_text(self) -> None:
        text = (
            "I analyzed the codebase and found an issue.\n\n"
            "QUESTION: The auth module uses JWT. Should I keep it?\n"
            "DEFAULT: Keep JWT as-is.\n\n"
            "Moving on to the next step..."
        )
        result = parse_question_block(text)
        assert result is not None
        question, _, default = result
        assert "JWT" in question
        assert "Keep" in default


# ── slack_post_and_get_reply ─────────────────────────────────


class TestSlackPostAndGetReply:
    @patch("morningstar.engine.time.sleep")
    @patch("morningstar.engine.httpx.get")
    @patch("morningstar.engine.httpx.post")
    def test_posts_and_gets_reply(
        self, mock_post: MagicMock, mock_get: MagicMock, mock_sleep: MagicMock,
    ) -> None:
        # chat.postMessage returns ts
        post_resp = MagicMock()
        post_resp.json.return_value = {"ok": True, "ts": "111.222"}
        mock_post.return_value = post_resp

        # conversations.replies returns a human reply
        get_resp = MagicMock()
        get_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"text": "Original question", "ts": "111.222"},
                {"text": "Use option B", "ts": "111.333", "user": "U_HUMAN"},
            ],
        }
        mock_get.return_value = get_resp

        answer = slack_post_and_get_reply(
            "xoxb-test-token", "C123", "Which option?",
            timeout_sec=60, poll_interval=10,
        )

        assert answer == "Use option B"
        mock_post.assert_called_once()
        mock_get.assert_called_once()

    @patch("morningstar.engine.time.sleep")
    @patch("morningstar.engine.httpx.get")
    @patch("morningstar.engine.httpx.post")
    def test_returns_none_on_timeout(
        self, mock_post: MagicMock, mock_get: MagicMock, mock_sleep: MagicMock,
    ) -> None:
        post_resp = MagicMock()
        post_resp.json.return_value = {"ok": True, "ts": "111.222"}
        mock_post.return_value = post_resp

        # No replies -- only the original message
        get_resp = MagicMock()
        get_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"text": "Original question", "ts": "111.222"},
            ],
        }
        mock_get.return_value = get_resp

        answer = slack_post_and_get_reply(
            "xoxb-test-token", "C123", "Question?",
            timeout_sec=60, poll_interval=30,
        )

        assert answer is None
        assert mock_get.call_count == 2  # 60/30 = 2 polls

    @patch("morningstar.engine.httpx.post")
    def test_returns_none_on_post_failure(self, mock_post: MagicMock) -> None:
        post_resp = MagicMock()
        post_resp.json.return_value = {"ok": False, "error": "channel_not_found"}
        mock_post.return_value = post_resp

        answer = slack_post_and_get_reply(
            "xoxb-test-token", "C_BAD", "Question?",
        )

        assert answer is None

    @patch("morningstar.engine.httpx.post")
    def test_returns_none_on_network_error(self, mock_post: MagicMock) -> None:
        import httpx
        mock_post.side_effect = httpx.TransportError("connection refused")

        answer = slack_post_and_get_reply(
            "xoxb-test-token", "C123", "Question?",
        )

        assert answer is None

    @patch("morningstar.engine.time.sleep")
    @patch("morningstar.engine.httpx.get")
    @patch("morningstar.engine.httpx.post")
    def test_filters_bot_own_message(
        self, mock_post: MagicMock, mock_get: MagicMock, mock_sleep: MagicMock,
    ) -> None:
        post_resp = MagicMock()
        post_resp.json.return_value = {"ok": True, "ts": "111.222"}
        mock_post.return_value = post_resp

        # First poll: only bot's message. Second poll: human replies.
        get_resp_1 = MagicMock()
        get_resp_1.json.return_value = {
            "ok": True,
            "messages": [{"text": "Question?", "ts": "111.222"}],
        }
        get_resp_2 = MagicMock()
        get_resp_2.json.return_value = {
            "ok": True,
            "messages": [
                {"text": "Question?", "ts": "111.222"},
                {"text": "Go with REST", "ts": "111.444"},
            ],
        }
        mock_get.side_effect = [get_resp_1, get_resp_2]

        answer = slack_post_and_get_reply(
            "xoxb-test-token", "C123", "Question?",
            timeout_sec=120, poll_interval=30,
        )

        assert answer == "Go with REST"
        assert mock_get.call_count == 2


# ── execute_task with question handling ───────────────────────


class TestExecuteTaskWithQuestions:
    @patch("morningstar.engine._git_commit")
    @patch("morningstar.engine.slack_post_and_get_reply")
    @patch("morningstar.engine._run_claude")
    def test_asks_slack_when_question_and_bot_token(
        self, mock_claude: MagicMock, mock_ask: MagicMock,
        mock_git: MagicMock, tmp_path: MagicMock,
    ) -> None:
        from morningstar.engine import execute_task

        log_dir = tmp_path / ".agent-logs"
        log_dir.mkdir()

        # First call returns a question
        mock_claude.side_effect = [
            {
                "result": "Partial work done.\nQUESTION: Use SQL or NoSQL?\nDEFAULT: SQL",
                "total_cost_usd": 2.0,
                "is_error": False,
                "session_id": "sess-question-12345678",
            },
            # Follow-up after answer
            {
                "result": "Completed with SQL",
                "total_cost_usd": 1.5,
                "is_error": False,
                "session_id": "sess-question-12345678",
            },
        ]
        mock_ask.return_value = "Use SQL please"

        result = execute_task(
            {"id": "q-task", "title": "DB choice", "description": "..."},
            repo_path=tmp_path,
            model="sonnet",
            budget_per_task=5.0,
            log_dir=log_dir,
            bot_token="xoxb-test-12345",
            slack_channel="C123",
            question_timeout=60,
        )

        assert result.success is True
        assert result.cost == 3.5  # 2.0 + 1.5
        mock_ask.assert_called_once()
        assert mock_claude.call_count == 2

    @patch("morningstar.engine._git_commit")
    @patch("morningstar.engine.slack_post")
    @patch("morningstar.engine._run_claude")
    def test_logs_question_without_bot_token(
        self, mock_claude: MagicMock, mock_slack: MagicMock,
        mock_git: MagicMock, tmp_path: MagicMock,
    ) -> None:
        from morningstar.engine import execute_task

        log_dir = tmp_path / ".agent-logs"
        log_dir.mkdir()

        mock_claude.return_value = {
            "result": "QUESTION: Which framework?\nDEFAULT: Express",
            "total_cost_usd": 1.0,
            "is_error": False,
            "session_id": "sess-noquestion-12345",
        }

        result = execute_task(
            {"id": "no-bot", "title": "Framework", "description": "..."},
            repo_path=tmp_path,
            model="sonnet",
            budget_per_task=5.0,
            log_dir=log_dir,
            bot_token=None,
            slack_webhook="https://hooks.slack.com/services/T1/B2/abc",
        )

        assert result.success is True
        # Should post question to webhook as fallback
        assert mock_slack.called

    @patch("morningstar.engine._git_commit")
    @patch("morningstar.engine._run_claude")
    def test_normal_flow_when_no_question(
        self, mock_claude: MagicMock, mock_git: MagicMock, tmp_path: MagicMock,
    ) -> None:
        from morningstar.engine import execute_task

        log_dir = tmp_path / ".agent-logs"
        log_dir.mkdir()

        mock_claude.return_value = {
            "result": "All done, tests passing.",
            "total_cost_usd": 2.0,
            "is_error": False,
            "session_id": "sess-normal-12345678",
        }

        result = execute_task(
            {"id": "normal-task", "title": "Simple", "description": "..."},
            repo_path=tmp_path,
            model="sonnet",
            budget_per_task=5.0,
            log_dir=log_dir,
            bot_token="xoxb-test-12345",
            slack_channel="C123",
        )

        assert result.success is True
        assert result.cost == 2.0
        assert mock_claude.call_count == 1  # No follow-up needed
