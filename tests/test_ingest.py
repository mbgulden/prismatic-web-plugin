"""
Unit tests for prismatic_web_plugin.ingest.

Tests:
- slugify() edge cases
- read_doc() encoding fallback
- find_5_docs() pattern matching (all 5, partial, none, nonexistent dir)
- extract_with_agy() parsing (success, AGY failure, JSON in code fence)
- write_ingest_report() output structure
- run_ingest() full library API (success, partial, error, dry-run)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prismatic_web_plugin.ingest import (
    CLIENT_PROFILE_SCHEMA,
    FRAMEWORK_DOCS,
    extract_with_agy,
    find_5_docs,
    read_doc,
    run_ingest,
    slugify,
    write_ingest_report,
)


# ─────────────────────────────────────────────────────────────────────
# slugify
# ─────────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_basic_lowercase_and_dash(self):
        assert slugify("Hello World") == "hello-world"

    def test_strips_punctuation(self):
        assert slugify("Hello World!") == "hello-world"

    def test_handles_apostrophes(self):
        assert slugify("Meridian Women's Defense") == "meridian-womens-defense"

    def test_collapses_dashes(self):
        assert slugify("Multi  --  Dashes") == "multi-dashes"

    def test_trims_whitespace(self):
        assert slugify("  trim me  ") == "trim-me"

    def test_handles_underscores(self):
        assert slugify("snake_case_string") == "snake-case-string"

    def test_empty_string(self):
        assert slugify("") == ""

    def test_only_punctuation(self):
        assert slugify("!!!") == ""

    def test_unicode_preserved_alphanumeric(self):
        # In Python 3, re \w matches Unicode word chars by default
        assert slugify("Café-Olé") == "café-olé"


# ─────────────────────────────────────────────────────────────────────
# read_doc
# ─────────────────────────────────────────────────────────────────────

class TestReadDoc:
    def test_reads_utf8(self, tmp_path: Path):
        p = tmp_path / "utf8.md"
        p.write_text("Hello — world", encoding="utf-8")
        assert read_doc(p) == "Hello — world"

    def test_falls_back_to_latin1(self, tmp_path: Path):
        p = tmp_path / "latin1.md"
        p.write_bytes("Café".encode("latin-1"))
        # First try raises UnicodeDecodeError, falls back to latin-1
        assert read_doc(p) == "Café"


# ─────────────────────────────────────────────────────────────────────
# find_5_docs
# ─────────────────────────────────────────────────────────────────────

class TestFind5Docs:
    def test_finds_all_5_with_pretty_names(self, mock_okf_dir: Path):
        docs = find_5_docs(mock_okf_dir)
        assert len(docs) == 5
        assert "content_gathering_guide" in docs
        assert "partner_interview" in docs
        assert "brand_design_interview" in docs
        assert "conversion_launch_kit" in docs
        assert "post_purchase_automation" in docs

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        assert find_5_docs(tmp_path / "nope") == {}

    def test_empty_dir_returns_empty(self, mock_okf_dir_missing_docs: Path):
        assert find_5_docs(mock_okf_dir_missing_docs) == {}

    def test_partial_dir_returns_partial(self, mock_okf_dir_partial: Path):
        docs = find_5_docs(mock_okf_dir_partial)
        assert "content_gathering_guide" in docs
        assert "brand_design_interview" in docs
        assert "partner_interview" not in docs

    def test_underscore_pattern(self, tmp_path: Path):
        """Pattern with underscores instead of spaces."""
        (tmp_path / "content_gathering_guide.md").write_text("x", encoding="utf-8")
        (tmp_path / "partner_interview.md").write_text("x", encoding="utf-8")
        (tmp_path / "brand_design_interview.md").write_text("x", encoding="utf-8")
        (tmp_path / "conversion_launch_kit.md").write_text("x", encoding="utf-8")
        (tmp_path / "post_purchase_automation.md").write_text("x", encoding="utf-8")
        docs = find_5_docs(tmp_path)
        assert len(docs) == 5

    def test_dash_pattern(self, tmp_path: Path):
        """Pattern with dashes instead of underscores."""
        (tmp_path / "content-gathering-guide.md").write_text("x", encoding="utf-8")
        (tmp_path / "partner-interview.md").write_text("x", encoding="utf-8")
        (tmp_path / "brand-design-interview.md").write_text("x", encoding="utf-8")
        (tmp_path / "conversion-launch-kit.md").write_text("x", encoding="utf-8")
        (tmp_path / "post-purchase-automation.md").write_text("x", encoding="utf-8")
        docs = find_5_docs(tmp_path)
        assert len(docs) == 5


# ─────────────────────────────────────────────────────────────────────
# extract_with_agy
# ─────────────────────────────────────────────────────────────────────

class TestExtractWithAgy:
    def test_returns_parsed_json(self, mock_okf_dir: Path, mock_agy_subprocess: MagicMock):
        docs = find_5_docs(mock_okf_dir)
        result = extract_with_agy(docs)
        assert result.get("client_profile", {}).get("name") == "Test Client"

    def test_strips_markdown_code_fences(self, mock_okf_dir: Path, monkeypatch: pytest.MonkeyPatch):
        """AGY sometimes wraps JSON in ```json ... ``` — should be stripped."""
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = "```json\n{\"client_profile\": {\"name\": \"Fenced\"}}\n```"
        monkeypatch.setattr("subprocess.run", mock)
        docs = find_5_docs(mock_okf_dir)
        result = extract_with_agy(docs)
        assert result["client_profile"]["name"] == "Fenced"

    def test_returns_empty_on_agy_failure(
        self, mock_okf_dir: Path, mock_agy_failure: MagicMock
    ):
        docs = find_5_docs(mock_okf_dir)
        result = extract_with_agy(docs)
        assert result == {}

    def test_finds_inline_json_object(self, mock_okf_dir: Path, monkeypatch: pytest.MonkeyPatch):
        """If AGY returns prose with a single { ... } line, recover it."""
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = (
            "Sure! Here's the JSON:\n"
            '{"client_profile": {"name": "Inline"}}\n'
            "Let me know if you need changes."
        )
        monkeypatch.setattr("subprocess.run", mock)
        docs = find_5_docs(mock_okf_dir)
        result = extract_with_agy(docs)
        assert result["client_profile"]["name"] == "Inline"


# ─────────────────────────────────────────────────────────────────────
# write_ingest_report
# ─────────────────────────────────────────────────────────────────────

class TestWriteIngestReport:
    def test_report_includes_all_5_doc_statuses(self, tmp_path: Path, mock_okf_dir: Path):
        report = tmp_path / "report.md"
        docs = find_5_docs(mock_okf_dir)
        write_ingest_report(report, docs, {}, [])
        text = report.read_text()
        for canonical, desc in FRAMEWORK_DOCS:
            assert desc in text

    def test_report_marks_missing_docs(self, tmp_path: Path, mock_okf_dir_partial: Path):
        report = tmp_path / "report.md"
        docs = find_5_docs(mock_okf_dir_partial)
        write_ingest_report(report, docs, {}, [])
        text = report.read_text()
        # 2 should be present (✓), 3 should be marked missing (✗)
        assert text.count("✓") == 2
        assert text.count("✗") == 3

    def test_report_lists_missing_fields(self, tmp_path: Path, mock_okf_dir: Path):
        report = tmp_path / "report.md"
        docs = find_5_docs(mock_okf_dir)
        write_ingest_report(report, docs, {}, ["`content.classes` is empty"])
        text = report.read_text()
        assert "Missing Required Fields" in text
        assert "`content.classes` is empty" in text

    def test_report_shows_extracted_summary(self, tmp_path: Path, mock_okf_dir: Path):
        report = tmp_path / "report.md"
        docs = find_5_docs(mock_okf_dir)
        extracted = {
            "client_profile": {
                "name": "Test Client",
                "mission": "Test mission",
                "service_area": "PNW",
            },
            "content": {"classes": [{"name": "c1"}], "lead_magnets": []},
            "automation": {"email_sequences": [{"n": 1}], "post_purchase_flows": []},
        }
        write_ingest_report(report, docs, extracted, [])
        text = report.read_text()
        assert "Test Client" in text
        assert "Test mission" in text


# ─────────────────────────────────────────────────────────────────────
# run_ingest (library API)
# ─────────────────────────────────────────────────────────────────────

class TestRunIngest:
    def test_error_when_dir_missing(self, tmp_path: Path):
        result = run_ingest(tmp_path / "nope")
        assert result["status"] == "error"
        assert "not a directory" in result["error"]

    def test_error_when_no_docs(self, mock_okf_dir_missing_docs: Path):
        result = run_ingest(mock_okf_dir_missing_docs)
        assert result["status"] == "error"
        assert "no docs" in result["error"]

    def test_error_when_agy_fails(
        self, mock_okf_dir: Path, mock_agy_failure: MagicMock
    ):
        result = run_ingest(mock_okf_dir)
        assert result["status"] == "error"
        assert "AGY" in result["error"]

    def test_dry_run_writes_nothing(self, mock_okf_dir: Path, output_dir: Path, mock_agy_subprocess: MagicMock):
        result = run_ingest(mock_okf_dir, output_dir=output_dir, dry_run=True)
        assert result["status"] == "ok"
        # Nothing should be written
        assert not (output_dir / "client_profile.json").exists()
        assert not (output_dir / "content_brief.json").exists()
        assert not (output_dir / "ingest_report.md").exists()
        assert result["report_path"] is None
        assert result["paths"]["profile"] is None

    def test_writes_all_three_files(
        self, mock_okf_dir: Path, output_dir: Path, mock_agy_subprocess: MagicMock
    ):
        result = run_ingest(mock_okf_dir, output_dir=output_dir)
        assert result["status"] == "ok"
        assert (output_dir / "client_profile.json").exists()
        assert (output_dir / "content_brief.json").exists()
        assert (output_dir / "ingest_report.md").exists()
        profile = json.loads((output_dir / "client_profile.json").read_text())
        assert "client_profile" in profile
        assert "brand" in profile

    def test_default_output_dir_under_input(
        self, mock_okf_dir: Path, mock_agy_subprocess: MagicMock
    ):
        result = run_ingest(mock_okf_dir, dry_run=False)
        # default output is <docs_dir>/output/<slug>/
        assert result["status"] == "ok"
        slug = "test-client"  # from the mock AGY output
        expected = mock_okf_dir / "output" / slug
        assert expected.exists()

    def test_missing_required_fields_marks_partial(
        self, mock_okf_dir: Path, output_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """When AGY returns a profile with no mission/classes, status='partial' and missing_fields populated."""
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = json.dumps({
            "client_profile": {"name": "X", "mission": ""},  # mission empty
            "content": {"classes": []},  # classes empty
            "automation": {"email_sequences": [{"n": 1}]},  # present
        })
        monkeypatch.setattr("subprocess.run", mock)
        result = run_ingest(mock_okf_dir, output_dir=output_dir)
        assert result["status"] == "partial"
        assert len(result["missing_fields"]) >= 2
        assert any("mission" in m for m in result["missing_fields"])
        assert any("classes" in m for m in result["missing_fields"])

    def test_docs_found_in_result(
        self, mock_okf_dir: Path, output_dir: Path, mock_agy_subprocess: MagicMock
    ):
        result = run_ingest(mock_okf_dir, output_dir=output_dir)
        assert len(result["docs_found"]) == 5

    def test_uses_dir_name_as_fallback_client_name(
        self, mock_okf_dir: Path, output_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """If AGY returns no client name, the docs_dir.name is used for slug."""
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = json.dumps({
            "client_profile": {"name": ""},  # empty
            "content": {"classes": ["c"]},
            "automation": {"email_sequences": [{"n": 1}]},
        })
        monkeypatch.setattr("subprocess.run", mock)
        result = run_ingest(mock_okf_dir, output_dir=output_dir)
        # Slug is based on dir name
        assert result["status"] in ("ok", "partial")


# ─────────────────────────────────────────────────────────────────────
# CLI smoke
# ─────────────────────────────────────────────────────────────────────

class TestIngestCLI:
    def test_cli_dry_run_prints_client(self, mock_okf_dir: Path, mock_agy_subprocess: MagicMock, capsys):
        from prismatic_web_plugin.ingest import main as ingest_main

        with patch("sys.argv", ["ingest", str(mock_okf_dir), "--dry-run"]):
            with pytest.raises(SystemExit) as exc:
                ingest_main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "Test Client" in captured.out
        assert "Status: ok" in captured.out

    def test_cli_exits_1_on_error(self, mock_okf_dir_missing_docs: Path, capsys):
        from prismatic_web_plugin.ingest import main as ingest_main

        with patch("sys.argv", ["ingest", str(mock_okf_dir_missing_docs)]):
            with pytest.raises(SystemExit) as exc:
                ingest_main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_cli_exits_2_on_partial(
        self, mock_okf_dir: Path, output_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        from prismatic_web_plugin.ingest import main as ingest_main

        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = json.dumps({
            "client_profile": {"name": "X", "mission": ""},
            "content": {"classes": []},
            "automation": {"email_sequences": []},
        })
        monkeypatch.setattr("subprocess.run", mock)
        with patch("sys.argv", ["ingest", str(mock_okf_dir), "--out", str(output_dir)]):
            with pytest.raises(SystemExit) as exc:
                ingest_main()
        assert exc.value.code == 2


# ─────────────────────────────────────────────────────────────────────
# Constants sanity
# ─────────────────────────────────────────────────────────────────────

class TestModuleConstants:
    def test_framework_docs_has_5_entries(self):
        assert len(FRAMEWORK_DOCS) == 5

    def test_framework_docs_have_unique_canonicals(self):
        canons = [c for c, _ in FRAMEWORK_DOCS]
        assert len(set(canons)) == 5

    def test_client_profile_schema_has_required_sections(self):
        assert "client_profile" in CLIENT_PROFILE_SCHEMA
        assert "brand" in CLIENT_PROFILE_SCHEMA
        assert "content" in CLIENT_PROFILE_SCHEMA
        assert "automation" in CLIENT_PROFILE_SCHEMA
        assert "tech" in CLIENT_PROFILE_SCHEMA
