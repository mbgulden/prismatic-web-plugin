
import pytest
import os
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_okf_dir(tmp_path):
    """
    Fixture to create a mock OKF directory structure for testing.
    """
    okf_path = tmp_path / "growthwebdev-knowledge/okf"
    okf_path.mkdir(parents=True)

    (okf_path / "integrations").mkdir()
    (okf_path / "integrations/pwp-config.yaml").write_text("key: value")

    (okf_path / "concepts").mkdir()
    (okf_path / "concepts/concept1.md").write_text("Concept 1 content")

    return okf_path

@pytest.fixture
def mock_linear_api():
    """
    Fixture to mock the Linear API client.
    """
    with patch('prismatic_web_plugin.distill.LinearClient') as mock_client:
        mock_client.return_value.issue.return_value = MagicMock(
            title="Mock Issue",
            description="Mock Description",
            state=MagicMock(name="Todo")
        )
        yield mock_client
