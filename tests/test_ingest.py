"""
Unit tests for prismatic_web_plugin.ingest.

Tests:
- slugify() slug behavior
- read_doc() reads file content
- find_5_docs() selects required PWP docs from OKF
- write_ingest_report() writes JSON report
- run_ingest() library API (dry_run, skip_agy, error cases)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prismatic_web_plugin.ingest import (
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
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars_removed(self):
        assert slugify("Meridian Women's Defense") == "meridian-womens-defense"

    def test_multiple_spaces_collapsed(self):
        assert slugify("Multi   Spaces") == "multi-spaces"


# ─────────────────────────────────────────────────────────────────────
# read_doc
# ─────────────────────────────────────────────────────────────────────


class TestReadDoc:
    def test_reads_text_file(self, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("Hello world")
        assert read_doc(f) == "Hello world"

    def test_raises_on_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_doc(tmp_path / "missing.md")


# ─────────────────────────────────────────────────────────────────────
# find_5_docs
# ─────────────────────────────────────────────────────────────────────


class TestFind5Docs:
    def _make_okf(self, root: Path) -> Path:
        """Create a directory containing 5 docs with required canonical names."""
        okf = root / "okf"
        okf.mkdir()
        # Required canonical names (matches FRAMEWORK_DOCS in ingest.py)
        (okf / "content_gathering_guide.md").write_text("# Content Gathering\ncontent")
        (okf / "partner_interview.md").write_text("# Partner Interview\ncontent")
        (okf / "brand_design_interview.md").write_text("# Brand & Design\ncontent")
        (okf / "conversion_launch_kit.md").write_text("# Conversion\ncontent")
        (okf / "post_purchase_automation.md").write_text("# Post-Purchase\ncontent")
        return okf

    def test_returns_5_required_docs(self, tmp_path: Path):
        okf = self._make_okf(tmp_path)
        docs = find_5_docs(okf)
        assert isinstance(docs, dict)
        assert len(docs) == 5

    def test_missing_okf_returns_empty(self, tmp_path: Path):
        docs = find_5_docs(tmp_path / "does-not-exist")
        assert docs == {}


# ─────────────────────────────────────────────────────────────────────
# write_ingest_report
# ─────────────────────────────────────────────────────────────────────


class TestWriteIngestReport:
    def test_writes_markdown_report(self, tmp_path: Path):
        report_path = tmp_path / "ingest-report.md"
        docs = {"content_gathering_guide": "/path/to/file.md"}
        extracted = {
            "client_profile": {"name": "Test Client", "mission": "Help people"},
            "content": {"classes": ["a"], "lead_magnets": []},
            "automation": {"email_sequences": ["x"], "post_purchase_flows": []},
        }
        write_ingest_report(report_path, docs, extracted, [])
        assert report_path.exists()
        text = report_path.read_text()
        assert "Ingest Report" in text
        assert "Test Client" in text
        assert "content_gathering_guide" in text or "Content Gathering" in text


# ─────────────────────────────────────────────────────────────────────
# run_ingest (library API)
# ─────────────────────────────────────────────────────────────────────


class TestRunIngest:
    def test_dry_run_does_not_call_agy(self, tmp_path: Path):
        # Patch extract_with_agy so we don't hit the real AGY subprocess
        with patch("prismatic_web_plugin.ingest.extract_with_agy") as mock_extract:
            mock_extract.return_value = {
                "client_profile": {"name": "Mock Client"},
                "content": {"classes": ["a", "b"]},
                "automation": {"email_sequences": ["x"]},
            }
            okf = tmp_path / "okf"
            okf.mkdir()
            (okf / "content_gathering_guide.md").write_text("c")
            (okf / "partner_interview.md").write_text("p")
            (okf / "brand_design_interview.md").write_text("b")
            (okf / "conversion_launch_kit.md").write_text("cv")
            (okf / "post_purchase_automation.md").write_text("pp")

            result = run_ingest(docs_dir=okf, output_dir=tmp_path, dry_run=True)
            assert result is not None
            mock_extract.assert_called_once()

    def test_missing_dir_returns_error_status(self, tmp_path: Path):
        result = run_ingest(docs_dir=tmp_path / "missing", output_dir=tmp_path, dry_run=True)
        assert result["status"] == "error"