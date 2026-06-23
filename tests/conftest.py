
import pytest
import os
import json
from pathlib import Path
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


@pytest.fixture
def mock_client_profile() -> dict:
    """
    Fixture providing a minimal but complete client_profile dict for
    synthesize/distill tests.
    """
    return {
        "client_profile": {
            "name": "Meridian Women's Defense Academy",
            "tagline": "Empowering women through self-defense training",
            "audience": "Women aged 25-55 in urban metro areas",
            "offerings": [
                {
                    "name": "Beginner Self-Defense (8-week course)",
                    "price": 295,
                    "format": "in-person group class",
                },
                {
                    "name": "Private 1:1 Sessions",
                    "price": 120,
                    "format": "in-person private",
                },
            ],
            "brand": {
                "colors": ["#1A1A1A", "#C9A961", "#F5F1E8"],
                "mood": "confident, warm, grounded",
            },
            "location": "Portland, OR",
            "domain": "meridianwomensdefense.com",
        },
        "build_plan": {
            "pages": [
                {"path": "/", "title": "Home"},
                {"path": "/about", "title": "About"},
                {"path": "/classes", "title": "Classes"},
                {"path": "/contact", "title": "Contact"},
            ],
            "automations": [
                {"name": "Lead Magnet Nurture", "trigger": "download_guide"},
            ],
        },
    }


@pytest.fixture
def mock_client_profile_path(tmp_path, mock_client_profile):
    """Path to a JSON file containing mock_client_profile."""
    p = tmp_path / "client_profile.json"
    p.write_text(json.dumps(mock_client_profile))
    return p


# ─────────────────────────────────────────────────────────────────────
# Distill-test fixtures
# ─────────────────────────────────────────────────────────────────────


_MOCK_BUILD_PLAN_MD = """\
# Meridian Women's Defense Academy: Comprehensive Website Build Plan

**URL:** https://meridianwomensdefense.com
**Client:** Meridian Women's Defense Academy

## 1. Site Architecture

### 1.1 Full Page List

* **`/` (Home):** Hero + intro + featured classes
* **`/about/` (About):** Story + instructor bios
* **`/classes/` (Classes):** Course catalog with pricing
* **`/workshops/` (Workshops):** One-off workshops and intensives
* **`/contact/` (Contact):** Form + location + hours
* **`/blog/` (Blog):** Articles and training tips

## 2. Per-Page Content Briefs

### Home

Hero copy for Meridian Women's Defense.

### About

About Meridian.

## 3. Design System Specifications

Colors: #1A1A1A, #C9A961, #F5F1E8

## 4. Asset Plan

Hero images, instructor portraits.

## 5. Technical Requirements

Astro / Cloudflare Pages.

## 6. Automation Workflows

### 6.1 Lead Magnet Nurture Workflow

Trigger: download_guide

### 6.2 Post-Purchase Onboarding Workflow

Trigger: course_purchase

## 7. Success Metrics

- 1000 visits / month
- 50 leads / month
- 10 bookings / month
"""


@pytest.fixture
def mock_build_plan_text() -> str:
    """Markdown text of a representative website_build_plan.md."""
    return _MOCK_BUILD_PLAN_MD


@pytest.fixture
def mock_build_plan_path(tmp_path) -> Path:
    """Path to a markdown file containing a build plan."""
    p = tmp_path / "website_build_plan.md"
    p.write_text(_MOCK_BUILD_PLAN_MD)
    return p


@pytest.fixture
def mock_linear_gql() -> MagicMock:
    """MagicMock stand-in for a Linear GraphQL response helper."""
    mock = MagicMock()
    mock.return_value = {"data": {"issueCreate": {"success": True, "issue": {"identifier": "GRO-1234"}}}}
    return mock


@pytest.fixture
def mock_load_api_key(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch distill.load_api_key to return a fake key."""
    mock = MagicMock(return_value="lin_api_FAKE_KEY_FOR_TESTS")
    monkeypatch.setattr("prismatic_web_plugin.distill.load_api_key", mock, raising=False)
    return mock
