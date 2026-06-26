"""
Integration tests for the run/watch/status CLI commands.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prismatic_web_plugin import builder
from prismatic_web_plugin.builder import main as builder_main


def _ok_ingest(output_dir: Path) -> dict:
    return {
        "status": "ok",
        "client_profile": {"name": "Test"},
        "paths": {
            "profile": str(output_dir / "client_profile.json"),
            "brief": str(output_dir / "content_brief.json"),
            "report": str(output_dir / "ingest_report.md"),
        },
    }


def _ok_synthesize(output_dir: Path) -> dict:
    return {
        "status": "ok",
        "word_count": 100,
        "path": str(output_dir / "website_build_plan.md"),
    }


def _ok_distill() -> dict:
    return {
        "status": "ok",
        "epic_id": "GRO-9999",
        "child_ids": ["GRO-10001"],
    }


class TestOrchestratorCLI:
    def test_run_command(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
        monkeypatch.setattr(builder, "OUTPUT_BASE", tmp_path)
        with patch.object(builder, "run_ingest", return_value=_ok_ingest(tmp_path)), \
             patch.object(builder, "run_synthesize", return_value=_ok_synthesize(tmp_path)), \
             patch.object(builder, "run_distill", return_value=_ok_distill()):
            with patch("sys.argv", ["pwb", "run", "--client", "test-client", "--skip-agy", "--dry-run"]):
                code = builder_main()
                assert code == 0
        captured = capsys.readouterr()
        assert "client_slug" in captured.out

    def test_status_command(self, monkeypatch: pytest.MonkeyPatch, capsys):
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})
        monkeypatch.setattr(builder, "_epic_status", lambda e, k: {
            "identifier": "GRO-123",
            "title": "Epic Title",
            "state": "In Progress",
            "children": [],
            "summary": {"total": 0, "done": 0, "in_progress": 0, "todo": 0, "canceled": 0, "backlog": 0},
        })
        with patch("sys.argv", ["pwb", "status", "--epic", "GRO-123"]):
            code = builder_main()
            assert code == 0
        captured = capsys.readouterr()
        assert "GRO-123" in captured.out

    def test_watch_command(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(builder, "load_env", lambda: {"LINEAR_API_KEY": "fake"})
        monkeypatch.setattr(builder, "watch_epic", MagicMock(return_value=0))
        with patch("sys.argv", ["pwb", "watch", "--epic", "GRO-123", "--interval", "1"]):
            code = builder_main()
            assert code == 0
        builder.watch_epic.assert_called_once_with("GRO-123", poll_interval=1, max_runtime=86400)
