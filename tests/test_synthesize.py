"""
Unit tests for prismatic_web_plugin.synthesize.

Tests:
- slugify() (re-exported)
- synthesize_stub() output structure
- run_synthesize() library API (skip_agy, dry_run, error cases)
- _call_agy() subprocess behavior (success, failure, code fence stripping)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prismatic_web_plugin.synthesize import (
    SYNTHESIS_PROMPT_TEMPLATE,
    _call_agy,
    run_synthesize,
    slugify,
    synthesize_stub,
)

# ─────────────────────────────────────────────────────────────────────
# slugify (re-exported in synthesize)
# ─────────────────────────────────────────────────────────────────────

class TestSlugifyReexport:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"


# ─────────────────────────────────────────────────────────────────────
# synthesize_stub
# ─────────────────────────────────────────────────────────────────────

class TestSynthesizeStub:
    def test_includes_client_name(self, mock_client_profile: dict):
        out = synthesize_stub(mock_client_profile)
        assert "Meridian Women's Defense Academy" in out

    def test_has_all_7_sections(self, mock_client_profile: dict):
        out = synthesize_stub(mock_client_profile)
        for i, section in enumerate([
            "Site Architecture",
            "Per-Page Content Briefs",
            "Design System Specifications",
            "Asset Plan",
            "Technical Requirements",
            "Automation Workflows",
            "Success Metrics",
        ], 1):
            assert f"## {i}. {section}" in out

    def test_marks_stub(self, mock_client_profile: dict):
        out = synthesize_stub(mock_client_profile)
        assert "stub" in out.lower()

    def test_handles_missing_name(self):
        profile = {"client_profile": {}}
        out = synthesize_stub(profile)
        assert "# Client" in out


# ─────────────────────────────────────────────────────────────────────
# _call_agy
# ─────────────────────────────────────────────────────────────────────

class TestCallAgy:
    def test_returns_agy_stdout(self, monkeypatch: pytest.MonkeyPatch):
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = "Some output text"
        monkeypatch.setattr("subprocess.run", mock)
        out = _call_agy("test prompt", model="test-model", timeout=60)
        assert out == "Some output text"

    def test_strips_markdown_code_fences(self, monkeypatch: pytest.MonkeyPatch):
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = "```markdown\n# Title\n```"
        monkeypatch.setattr("subprocess.run", mock)
        out = _call_agy("prompt", timeout=60)
        assert out == "# Title"

    def test_strips_plain_code_fences(self, monkeypatch: pytest.MonkeyPatch):
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = "```\n# Title\n```"
        monkeypatch.setattr("subprocess.run", mock)
        out = _call_agy("prompt", timeout=60)
        assert out == "# Title"

    def test_raises_on_nonzero_exit(self, monkeypatch: pytest.MonkeyPatch):
        mock = MagicMock()
        mock.return_value.returncode = 1
        mock.return_value.stderr = "fatal: something broke"
        monkeypatch.setattr("subprocess.run", mock)
        with pytest.raises(RuntimeError) as exc:
            _call_agy("prompt", timeout=60)
        assert "AGY error" in str(exc.value)

    def test_raises_on_empty_output(self, monkeypatch: pytest.MonkeyPatch):
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = ""
        monkeypatch.setattr("subprocess.run", mock)
        with pytest.raises(RuntimeError) as exc:
            _call_agy("prompt", timeout=60)
        assert "empty" in str(exc.value).lower()


# ─────────────────────────────────────────────────────────────────────
# run_synthesize
# ─────────────────────────────────────────────────────────────────────

class TestRunSynthesize:
    def _write_profile(self, tmp_path: Path, profile: dict) -> Path:
        p = tmp_path / "client_profile.json"
        p.write_text(json.dumps(profile), encoding="utf-8")
        return p

    def test_error_when_profile_missing(self, tmp_path: Path):
        result = run_synthesize(tmp_path / "nope.json")
        assert result["status"] == "error"
        assert "not a file" in result["error"].lower()

    def test_skip_agy_writes_stub(self, mock_client_profile: dict, tmp_path: Path):
        profile = self._write_profile(tmp_path, mock_client_profile)
        out = tmp_path / "out"
        out.mkdir()
        result = run_synthesize(profile, output_dir=out, skip_agy=True)
        assert result["status"] == "ok"
        plan = (out / "website_build_plan.md").read_text()
        assert "Meridian Women's Defense Academy" in plan
        assert "stub" in plan.lower()

    def test_dry_run_writes_nothing(self, mock_client_profile: dict, tmp_path: Path):
        profile = self._write_profile(tmp_path, mock_client_profile)
        out = tmp_path / "out"
        out.mkdir()
        result = run_synthesize(profile, output_dir=out, skip_agy=True, dry_run=True)
        assert result["status"] == "ok"
        assert not (out / "website_build_plan.md").exists()
        assert result["path"] is None

    def test_full_pipeline_writes_real_plan(
        self, mock_client_profile: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        profile = self._write_profile(tmp_path, mock_client_profile)
        out = tmp_path / "out"
        out.mkdir()

        # Mock AGY to return a realistic plan
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = (
            "# Meridian Women's Defense Academy: Comprehensive Website Build Plan\n\n"
            "## 1. Site Architecture\n\nFull page list here\n"
        )
        monkeypatch.setattr("subprocess.run", mock)

        result = run_synthesize(profile, output_dir=out)
        assert result["status"] == "ok"
        assert (out / "website_build_plan.md").exists()
        text = (out / "website_build_plan.md").read_text()
        assert "Site Architecture" in text
        assert "Meridian" in text

    def test_error_on_agy_failure(
        self, mock_client_profile: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        profile = self._write_profile(tmp_path, mock_client_profile)
        out = tmp_path / "out"
        out.mkdir()

        mock = MagicMock()
        mock.return_value.returncode = 1
        mock.return_value.stderr = "network error"
        monkeypatch.setattr("subprocess.run", mock)

        result = run_synthesize(profile, output_dir=out)
        assert result["status"] == "error"
        assert "AGY" in result["error"]

    def test_default_output_dir(
        self, mock_client_profile: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        profile = self._write_profile(tmp_path, mock_client_profile)
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = "# Plan\nstuff"
        monkeypatch.setattr("subprocess.run", mock)

        result = run_synthesize(profile, skip_agy=False)
        # Default output dir is the same as the profile's dir
        assert result["status"] == "ok"
        assert (profile.parent / "website_build_plan.md").exists()

    def test_result_includes_path(
        self, mock_client_profile: dict, tmp_path: Path
    ):
        profile = self._write_profile(tmp_path, mock_client_profile)
        out = tmp_path / "out"
        out.mkdir()
        result = run_synthesize(profile, output_dir=out, skip_agy=True)
        assert "path" in result
        assert result["path"] is not None
        assert result["path"].endswith("website_build_plan.md")

    def test_invalid_json_profile(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("not json {", encoding="utf-8")
        result = run_synthesize(p)
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────
# CLI smoke
# ─────────────────────────────────────────────────────────────────────

class TestSynthesizeCLI:
    def test_cli_skip_agy_writes_stub(
        self, mock_client_profile: dict, tmp_path: Path, capsys
    ):
        from prismatic_web_plugin.synthesize import main as synth_main
        profile = tmp_path / "client_profile.json"
        profile.write_text(json.dumps(mock_client_profile), encoding="utf-8")
        out = tmp_path / "out"
        out.mkdir()

        with patch("sys.argv", ["synthesize", str(profile), "--out", str(out), "--no-agy"]):
            with pytest.raises(SystemExit) as exc:
                synth_main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert (out / "website_build_plan.md").exists()
        assert "Wrote" in captured.out

    def test_cli_exits_1_on_error(self, tmp_path: Path, capsys):
        from prismatic_web_plugin.synthesize import main as synth_main
        with patch("sys.argv", ["synthesize", str(tmp_path / "nope.json")]):
            with pytest.raises(SystemExit) as exc:
                synth_main()
        assert exc.value.code == 1


# ─────────────────────────────────────────────────────────────────────
# Prompt template
# ─────────────────────────────────────────────────────────────────────

class TestPromptTemplate:
    def test_template_has_placeholder(self):
        assert "{client_profile}" in SYNTHESIS_PROMPT_TEMPLATE

    def test_template_mentions_7_sections(self):
        text = SYNTHESIS_PROMPT_TEMPLATE.lower()
        assert "site architecture" in text
        assert "design system" in text
        assert "technical" in text
        assert "automation" in text
        assert "success metrics" in text
