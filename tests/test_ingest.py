
import pytest
from unittest.mock import MagicMock, patch
import os
from prismatic_web_plugin import ingest

def test_load_okf_config_success(mock_okf_dir):
    config_path = mock_okf_dir / "integrations/pwp-config.yaml"
    config = ingest.load_okf_config(str(config_path))
    assert config == {"key": "value"}

def test_load_okf_config_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest.load_okf_config(str(tmp_path / "non_existent.yaml"))

def test_load_okf_document_success(mock_okf_dir):
    doc_path = mock_okf_dir / "concepts/concept1.md"
    content = ingest.load_okf_document(str(doc_path))
    assert content == "Concept 1 content"

def test_load_okf_document_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest.load_okf_document(str(tmp_path / "non_existent.md"))

def test_scan_okf_for_pwp_context(mock_okf_dir):
    # Simulate some pwp-specific files and general files
    (mock_okf_dir / "integrations/pwp_specific_doc.md").write_text("PWP specific content")
    (mock_okf_dir / "guides/general_guide.md").write_text("General guide content")

    # Mock the search_files tool
    with patch('prismatic_web_plugin.ingest.search_files') as mock_search:
        mock_search.return_value = {
            'results': [
                {'path': str(mock_okf_dir / "integrations/pwp_specific_doc.md")},
                {'path': str(mock_okf_dir / "integrations/pwp-config.yaml")},
                {'path': str(mock_okf_dir / "concepts/concept1.md")},
                {'path': str(mock_okf_dir / "guides/general_guide.md")}
            ]
        }
        
        # Mock read_file for each of the returned paths
        with patch('prismatic_web_plugin.ingest.read_file') as mock_read_file:
            def read_side_effect(path, **kwargs):
                if "pwp_specific_doc.md" in path:
                    return {'content': 'PWP specific content'}
                elif "pwp-config.yaml" in path:
                    return {'content': 'key: value'}
                elif "concept1.md" in path:
                    return {'content': 'Concept 1 content'}
                elif "general_guide.md" in path:
                    return {'content': 'General guide content'}
                return {'content': ''}
            mock_read_file.side_effect = read_side_effect

            pwp_context_docs = ingest.scan_okf_for_pwp_context(str(mock_okf_dir))
            assert len(pwp_context_docs) == 4 # All files should be returned as context
            assert "PWP specific content" in pwp_context_docs[str(mock_okf_dir / "integrations/pwp_specific_doc.md")]




