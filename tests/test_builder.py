"""
Integration tests for prismatic_web_plugin.builder (the PWP orchestrator).

Tests:
- run_pipeline() full flow: ingest → synthesize → distill (all mocked)
- run_pipeline() error propagation from each stage
- run_pipeline() with skip_agy and dry_run
- _epic_status() parsing Linear's response
- _post_progress_comment() HTTP call
- print_status() CLI
- main() arg parsing
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prismatic_web_plugin import builder
from prismatic_web_plugin.builder import (
    _epic_status,
    run_pipeline,
)


# ─────────────────────────────────────────────────────────────────────
# run_pipeline (mocked library calls)
# ─────────────────────────────────────────────────────────────────────

def _ok_ingest(output_dir: Path, **overrides) -> dict:
    base = {
        "status": "ok",
        "client_profile": {"name": "Test"},
        "content_brief": {},
        "report_path": str(output_dir / "ingest_report.md"),
        "paths": {
            "profile": str(output_dir / "client_profile.json"),
            "brief": str(output_dir / "content_brief.json"),
            "report": str(output_dir / "ingest_report.md"),
        },
        "missing_fields": [],
        "docs_found": ["content_gathering_guide"],
    }
    base.update(overrides)
    return base


def _ok_synthesize(output_dir: Path, **overrides) -> dict:
    plan_path = output_dir / "website_build_plan.md"
    plan_path.write_text("# Test Build Plan\nstuff", encoding="utf-8")
    base = {
        "status": "ok",
        "word_count": 100,
        "path": str(plan_path),
    }
    base.update(overrides)
    return base


def _ok_distill(**overrides) -> dict:
    base = {
        "status": "ok",
        "epic_id": "GRO-9999",
        "child_ids": ["GRO-10001", "GRO-10002"],
        "parsed": {"client_name": "Test", "pages": [], "phases": [], "automations": []},
    }
    base.update(overrides)
    return base


class TestRunPipeline:
    def test_full_pipeline_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """All 3 stages mocked to return success."""
        # Patch OUTPUT_BASE to use a tmp dir
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        # And okf_projects to a tmp path (it constructs docs_dir from it)
        fake_okf = tmp_path / "fake_okf"
        fake_okf.mkdir()
        # Patch Path so /home/ubuntu/work/growthwebdev-knowledge resolves to fake_okf
        # Instead, just patch the docs_dir construction by mocking run_ingest directly

        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)) as m_ingest, \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)) as m_synth, \
             patch.object(builder, "run_distill", return_value=_ok_distill()) as m_distill:
            result = run_pipeline("test-client", skip_agy=False, dry_run=False)

        assert result["status"] == "ok"
        assert result["client_slug"] == "test-client"
        assert "ingest" in result["stages"]
        assert "synthesize" in result["stages"]
        assert "distill" in result["stages"]
        assert result["epic_id"] == "GRO-9999"
        assert len(result["child_ids"]) == 2

    def test_ingest_failure_aborts_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value={"status": "error", "error": "no docs"}) as m_ingest, \
             patch.object(builder, "run_synthesize") as m_synth, \
             patch.object(builder, "run_distill") as m_distill:
            result = run_pipeline("test-client")

        assert result["status"] == "failed"
        assert result["stages"]["ingest"]["status"] == "error"
        # Synthesize and distill should NOT be called
        m_synth.assert_not_called()
        m_distill.assert_not_called()

    def test_ingest_partial_records_but_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Partial status (not error) continues to next stage."""
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path, status="partial", missing_fields=["x"])), \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)), \
             patch.object(builder, "run_distill", return_value=_ok_distill()):
            result = run_pipeline("test-client")

        # The pipeline should still complete ok if all 3 stages succeed
        assert result["status"] == "ok"
        assert "missing_fields" in result["stages"]["ingest"]

    def test_synthesize_failure_aborts_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)), \
             patch.object(builder, "run_synthesize", return_value={"status": "error", "error": "AGY died"}), \
             patch.object(builder, "run_distill") as m_distill:
            result = run_pipeline("test-client")

        assert result["status"] == "failed"
        assert result["stages"]["synthesize"]["status"] == "error"
        m_distill.assert_not_called()

    def test_distill_failure_aborts_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)), \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)), \
             patch.object(builder, "run_distill", return_value={"status": "error", "error": "Linear API down"}):
            result = run_pipeline("test-client")

        assert result["status"] == "failed"
        assert result["stages"]["distill"]["status"] == "error"

    def test_dry_run_passed_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)) as m_ingest, \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)), \
             patch.object(builder, "run_distill", return_value=_ok_distill()):
            run_pipeline("test-client", dry_run=True)

        # Verify dry_run was passed to ingest
        kwargs = m_ingest.call_args.kwargs
        assert kwargs.get("dry_run") is True

    def test_skip_agy_passed_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)), \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)) as m_synth, \
             patch.object(builder, "run_distill", return_value=_ok_distill()):
            run_pipeline("test-client", skip_agy=True)

        # Verify skip_agy was passed to synthesize
        kwargs = m_synth.call_args.kwargs
        assert kwargs.get("skip_agy") is True

    def test_result_includes_timestamps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)), \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)), \
             patch.object(builder, "run_distill", return_value=_ok_distill()):
            result = run_pipeline("test-client")

        assert "started_at" in result
        assert "finished_at" in result

    def test_ingest_exception_caught(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """If run_ingest raises unexpectedly, the pipeline catches and reports."""
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", side_effect=RuntimeError("explosion")):
            result = run_pipeline("test-client")

        assert result["status"] == "failed"
        assert "explosion" in result["stages"]["ingest"]["error"]


# ─────────────────────────────────────────────────────────────────────
# _epic_status (Linear HTTP)
# ─────────────────────────────────────────────────────────────────────

class TestEpicStatus:
    def test_parses_linear_response(self, monkeypatch: pytest.MonkeyPatch):
        fake_response = {
            "data": {
                "issue": {
                    "identifier": "GRO-9999",
                    "title": "Test Epic",
                    "state": {"name": "In Progress"},
                    "children": {
                        "nodes": [
                            {"identifier": "GRO-10001", "title": "Page 1", "state": {"name": "Done"}},
                            {"identifier": "GRO-10002", "title": "Page 2", "state": {"name": "In Progress"}},
                            {"identifier": "GRO-10003", "title": "Page 3", "state": {"name": "Todo"}},
                        ]
                    }
                }
            }
        }
        captured = {}

        class FakeResp:
            def __init__(self):
                self._data = json.dumps(fake_response).encode()
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.headers)
            captured["body"] = json.loads(req.data.decode())
            return FakeResp()

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        status = _epic_status("GRO-9999", "fake-key")

        assert status["identifier"] == "GRO-9999"
        assert status["state"] == "In Progress"
        assert status["summary"]["total"] == 3
        assert status["summary"]["done"] == 1
        assert status["summary"]["in_progress"] == 1
        assert status["summary"]["todo"] == 1
        assert status["summary"]["canceled"] == 0
        # Verify request was constructed correctly
        assert captured["url"] == "https://api.linear.app/graphql"
        assert captured["headers"]["Authorization"] == "fake-key"
        assert captured["body"]["variables"]["id"] == "GRO-9999"

    def test_handles_empty_children(self, monkeypatch: pytest.MonkeyPatch):
        fake_response = {
            "data": {
                "issue": {
                    "identifier": "GRO-9999",
                    "title": "Empty Epic",
                    "state": {"name": "Todo"},
                    "children": {"nodes": []}
                }
            }
        }

        class FakeResp:
            def __init__(self):
                self._data = json.dumps(fake_response).encode()
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=None):
            return FakeResp()

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        status = _epic_status("GRO-9999", "fake-key")
        assert status["summary"]["total"] == 0
        assert status["summary"]["done"] == 0


# ─────────────────────────────────────────────────────────────────────
# _post_progress_comment
# ─────────────────────────────────────────────────────────────────────

class TestPostProgressComment:
    def test_posts_comment_with_summary(self, monkeypatch: pytest.MonkeyPatch):
        from prismatic_web_plugin.builder import _post_progress_comment
        captured = {}

        class FakeResp:
            def read(self):
                return b'{"data": {"commentCreate": {"success": true}}}'
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            captured["headers"] = dict(req.headers)
            return FakeResp()

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        status = {
            "summary": {"total": 10, "done": 3, "in_progress": 2, "todo": 5, "canceled": 0, "backlog": 0}
        }
        _post_progress_comment("epic-uuid", status, "fake-key")

        # Verify the body has the right content
        body_text = captured["body"]["variables"]["body"]
        assert "3/10" in body_text
        assert "30%" in body_text
        assert "In Progress" in body_text or "in_progress" in body_text
        assert captured["headers"]["Authorization"] == "fake-key"


# ─────────────────────────────────────────────────────────────────────
# watch_epic (loop logic)
# ─────────────────────────────────────────────────────────────────────

class TestWatchEpic:
    def test_returns_1_when_no_api_key(self, monkeypatch: pytest.MonkeyPatch):
        from prismatic_web_plugin.builder import watch_epic
        monkeypatch.setattr(builder, "load_env", lambda: {})  # no LINEAR_API_KEY
        result = watch_epic("epic-uuid", poll_interval=1, max_runtime=1)
        assert result == 1

    def test_returns_0_when_all_children_done(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from prismatic_web_plugin.builder import watch_epic
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})

        # Patch _epic_status to return all-done children on first call
        done_status = {
            "identifier": "GRO-1",
            "title": "Epic",
            "state": "In Progress",
            "children": [
                {"id": "GRO-2", "title": "Page 1", "state": "Done"},
                {"id": "GRO-3", "title": "Page 2", "state": "Done"},
            ],
            "summary": {"total": 2, "done": 2, "in_progress": 0, "todo": 0, "canceled": 0, "backlog": 0},
        }
        monkeypatch.setattr(builder, "_epic_status", lambda epic, key: done_status)
        # Skip the progress comment
        monkeypatch.setattr(builder, "_post_progress_comment", lambda *a, **k: None)
        # Also patch time.sleep to be fast
        monkeypatch.setattr("time.sleep", lambda x: None)

        result = watch_epic("epic-uuid", poll_interval=1, max_runtime=60)
        assert result == 0

    def test_handles_status_fetch_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """If _epic_status raises, watch should log and continue (not crash)."""
        from prismatic_web_plugin.builder import watch_epic
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})

        call_count = [0]
        def flaky_status(epic, key):
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("transient")
            return {
                "identifier": "GRO-1",
                "title": "Epic",
                "state": "Done",
                "children": [{"id": "GRO-2", "title": "X", "state": "Done"}],
                "summary": {"total": 1, "done": 1, "in_progress": 0, "todo": 0, "canceled": 0, "backlog": 0},
            }
        monkeypatch.setattr(builder, "_epic_status", flaky_status)
        monkeypatch.setattr(builder, "_post_progress_comment", lambda *a, **k: None)
        monkeypatch.setattr("time.sleep", lambda x: None)

        result = watch_epic("epic-uuid", poll_interval=1, max_runtime=60)
        assert result == 0  # eventually all-done
        assert call_count[0] >= 2  # had to retry at least once

    def test_returns_2_on_max_runtime(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from prismatic_web_plugin.builder import watch_epic
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})

        # Always return "in progress" to prevent early exit
        in_progress_status = {
            "identifier": "GRO-1",
            "title": "Epic",
            "state": "In Progress",
            "children": [{"id": "GRO-2", "title": "X", "state": "In Progress"}],
            "summary": {"total": 1, "done": 0, "in_progress": 1, "todo": 0, "canceled": 0, "backlog": 0},
        }
        monkeypatch.setattr(builder, "_epic_status", lambda e, k: in_progress_status)
        monkeypatch.setattr(builder, "_post_progress_comment", lambda *a, **k: None)
        # Patch time.time to simulate passage of time
        counter = [0]
        def fake_time():
            counter[0] += 1
            return counter[0] * 100  # always returns larger values
        monkeypatch.setattr("time.time", fake_time)
        # sleep noop
        monkeypatch.setattr("time.sleep", lambda x: None)

        result = watch_epic("epic-uuid", poll_interval=1, max_runtime=50)
        assert result == 2  # max runtime hit

    def test_handles_post_comment_error(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """If posting the comment fails, log and continue."""
        from prismatic_web_plugin.builder import watch_epic
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})

        done_status = {
            "identifier": "GRO-1",
            "title": "Epic",
            "state": "Done",
            "children": [{"id": "GRO-2", "title": "X", "state": "Done"}],
            "summary": {"total": 1, "done": 1, "in_progress": 0, "todo": 0, "canceled": 0, "backlog": 0},
        }
        monkeypatch.setattr(builder, "_epic_status", lambda e, k: done_status)
        # Post fails
        def bad_post(*a, **k):
            raise RuntimeError("post failed")
        monkeypatch.setattr(builder, "_post_progress_comment", bad_post)
        monkeypatch.setattr("time.sleep", lambda x: None)

        result = watch_epic("epic-uuid", poll_interval=1, max_runtime=60)
        assert result == 0  # should still return 0

    def test_treats_canceled_as_terminal(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Canceled children count as done for watch purposes."""
        from prismatic_web_plugin.builder import watch_epic
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})

        status = {
            "identifier": "GRO-1",
            "title": "Epic",
            "state": "Done",
            "children": [
                {"id": "GRO-2", "title": "X", "state": "Done"},
                {"id": "GRO-3", "title": "Y", "state": "Canceled"},
            ],
            "summary": {"total": 2, "done": 1, "in_progress": 0, "todo": 0, "canceled": 1, "backlog": 0},
        }
        monkeypatch.setattr(builder, "_epic_status", lambda e, k: status)
        monkeypatch.setattr(builder, "_post_progress_comment", lambda *a, **k: None)
        monkeypatch.setattr("time.sleep", lambda x: None)

        result = watch_epic("epic-uuid", poll_interval=1, max_runtime=60)
        assert result == 0


# ─────────────────────────────────────────────────────────────────────
# print_status
# ─────────────────────────────────────────────────────────────────────

class TestPrintStatus:
    def test_prints_summary(self, monkeypatch: pytest.MonkeyPatch, capsys):
        from prismatic_web_plugin.builder import print_status
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})
        monkeypatch.setattr(builder, "_epic_status", lambda e, k: {
            "identifier": "GRO-9999",
            "title": "Test Epic",
            "state": "In Progress",
            "children": [
                {"id": "GRO-1", "title": "Page 1", "state": "Done"},
                {"id": "GRO-2", "title": "Page 2", "state": "Todo"},
            ],
            "summary": {"total": 2, "done": 1, "in_progress": 0, "todo": 1, "canceled": 0, "backlog": 0},
        })
        result = print_status("epic-uuid")
        captured = capsys.readouterr()
        assert "GRO-9999" in captured.out
        assert "Test Epic" in captured.out
        assert "Done" in captured.out
        assert "Todo" in captured.out
        assert result == 0

    def test_returns_1_when_no_api_key(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        from prismatic_web_plugin.builder import print_status
        monkeypatch.setattr(builder, "load_env", lambda: {})
        result = print_status("epic-uuid")
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert result == 1


# ─────────────────────────────────────────────────────────────────────
# main() CLI
# ─────────────────────────────────────────────────────────────────────

class TestBuilderCLI:
    def test_run_command(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)), \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)), \
             patch.object(builder, "run_distill", return_value=_ok_distill()):
            with patch("sys.argv", ["pwb", "run", "--client", "test-client", "--skip-agy", "--dry-run"]):
                from prismatic_web_plugin.builder import main as builder_main
                builder_main()
        captured = capsys.readouterr()
        # The result is dumped as JSON
        assert "client_slug" in captured.out
        assert "test-client" in captured.out

    def test_status_command(self, monkeypatch: pytest.MonkeyPatch, capsys):
        from prismatic_web_plugin.builder import main as builder_main
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})
        monkeypatch.setattr(builder, "_epic_status", lambda e, k: {
            "identifier": "GRO-1",
            "title": "Epic",
            "state": "In Progress",
            "children": [],
            "summary": {"total": 0, "done": 0, "in_progress": 0, "todo": 0, "canceled": 0, "backlog": 0},
        })
        with patch("sys.argv", ["pwb", "status", "--epic", "epic-uuid"]):
            result = builder_main()
        captured = capsys.readouterr()
        assert "GRO-1" in captured.out
        assert result == 0


# ─────────────────────────────────────────────────────────────────────
# load_env
# ─────────────────────────────────────────────────────────────────────

class TestLoadEnv:
    def test_loads_env_from_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "LINEAR_API_KEY=lin_api_TEST\n"
            "OTHER=value\n"
        )
        # Patch the env path constant
        from prismatic_web_plugin import builder
        original_path = builder.Path
        def patched_path(p):
            if ".hermes/profiles/orchestrator/.env" in str(p):
                return env_file
            return original_path(p)
        monkeypatch.setattr(builder, "Path", patched_path)
        env = builder.load_env()
        assert env.get("LINEAR_API_KEY") == "lin_api_TEST"
        assert env.get("OTHER") == "value"

    def test_returns_empty_when_file_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from prismatic_web_plugin import builder
        original_path = builder.Path
        def patched_path(p):
            if ".hermes/profiles/orchestrator/.env" in str(p):
                return tmp_path / "nonexistent.env"
            return original_path(p)
        monkeypatch.setattr(builder, "Path", patched_path)
        env = builder.load_env()
        assert env == {}

    def test_skips_comments_and_blank_lines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from prismatic_web_plugin import builder
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\n"
            "\n"
            "LINEAR_API_KEY=lin_api_TEST\n"
            "# Another comment\n"
        )
        original_path = builder.Path
        def patched_path(p):
            if ".hermes/profiles/orchestrator/.env" in str(p):
                return env_file
            return original_path(p)
        monkeypatch.setattr(builder, "Path", patched_path)
        env = builder.load_env()
        assert env.get("LINEAR_API_KEY") == "lin_api_TEST"
        assert len(env) == 1

    def test_strips_quotes_from_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from prismatic_web_plugin import builder
        env_file = tmp_path / ".env"
        env_file.write_text('LINEAR_API_KEY="lin_api_QUOTED"\n')
        original_path = builder.Path
        def patched_path(p):
            if ".hermes/profiles/orchestrator/.env" in str(p):
                return env_file
            return original_path(p)
        monkeypatch.setattr(builder, "Path", patched_path)
        env = builder.load_env()
        assert env.get("LINEAR_API_KEY") == "lin_api_QUOTED"
