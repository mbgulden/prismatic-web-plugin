from __future__ import annotations

import json
from pathlib import Path

from prismatic_web_plugin.astro_emdash import (
    EMDASH_VERSION,
    build_site_model,
    render_starter_files,
    scaffold_astro_emdash_site,
)


def _valkyrie_profile() -> dict:
    return {
        "client_profile": {
            "name": "Valkyrie Arms Training",
            "slug": "valkyrie-arms-training",
            "domain": "valkyriearmstraining.com",
            "phone": "(208) 813-8780",
            "address": "272 SW 5th Ave #400, Meridian, ID, USA",
            "tagline": "Responsible training. Confidence. Preparedness. Community.",
            "brand": {"colors": ["#0c0d0f", "#c6a86b"]},
        }
    }


def _expected_phone_href(prefix: str) -> str:
    # Construct from parts to avoid terminal/log redaction rewriting phone-like literals.
    return prefix + "+" + "1" + "208" + "813" + "8780"


def test_build_site_model_marks_emergency_placeholder_as_disposable():
    model = build_site_model(_valkyrie_profile(), placeholder_only=True)

    assert model.slug == "valkyrie-arms-training"
    assert model.placeholder_only is True
    assert model.source_note == "placeholder/emergency"
    assert model.primary_cta_href == _expected_phone_href("tel:")
    assert model.secondary_cta_href == _expected_phone_href("sms:")


def test_render_starter_files_uses_astro_and_emdash():
    model = build_site_model(_valkyrie_profile(), placeholder_only=True)
    files = render_starter_files(model)

    package = json.loads(files["package.json"])
    assert package["dependencies"]["astro"].startswith("^7")
    assert package["dependencies"]["emdash"] == EMDASH_VERSION
    assert package["dependencies"]["@emdash-cms/cloudflare"] == EMDASH_VERSION
    assert "import emdash from 'emdash/astro';" in files["astro.config.mjs"]
    assert "import { d1, kvCache, r2 } from '@emdash-cms/cloudflare';" in files["astro.config.mjs"]
    assert "data-placeholder-only" in files["src/pages/index.astro"]
    wrangler = json.loads(files["wrangler.jsonc"])
    assert wrangler["compatibility_flags"] == ["nodejs_compat"]


def test_render_starter_files_includes_pwp_approval_metadata():
    """GRO-2505: every generated site must carry approval metadata + a rollback command."""
    model = build_site_model(_valkyrie_profile(), placeholder_only=False)
    files = render_starter_files(model)

    # 1) Top-level site.json carries an embedded pwpApproval block.
    site = json.loads(files["src/data/site.json"])
    approval = site["pwpApproval"]
    assert approval["styleGuideVersion"]
    assert approval["contentModelVersion"]
    assert approval["approvalState"] == "pending"
    assert approval["requiresApprovalForProduction"] is True
    assert "rollback" in approval["rollbackCommand"].lower()

    # 2) A separate, discoverable pwp-approval.json is written at the project root.
    standalone = json.loads(files["pwp-approval.json"])
    assert standalone["client_slug"] == "valkyrie-arms-training"
    assert standalone["approval_state"] == "pending"
    assert standalone["requires_approval_for_production"] is True
    assert standalone["style_guide_version"] == approval["styleGuideVersion"]
    assert standalone["content_model_version"] == approval["contentModelVersion"]
    assert standalone["okf_paths"], "OKF evidence paths must be embedded in the scaffold"
    assert standalone["rollback_command"].startswith(
        "PYTHONPATH=src python3 -m prismatic_web_plugin.approval rollback"
    )


def test_starter_seed_encodes_placeholder_policy():
    model = build_site_model(_valkyrie_profile(), placeholder_only=True)
    files = render_starter_files(model)
    site = json.loads(files["src/data/site.json"])
    assert site["placeholderOnly"] is True
    assert site["pwpPolicy"]["emergencyPlaceholdersDoNotSetStandards"] is True
    assert site["pwpPolicy"]["editableStack"] == "Astro + EmDash"


def test_scaffold_astro_emdash_site_writes_expected_tree(tmp_path: Path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(_valkyrie_profile()))
    out = tmp_path / "site"

    result = scaffold_astro_emdash_site(profile, out, placeholder_only=False, overwrite=True)

    assert result["status"] == "ok"
    assert (out / "package.json").exists()
    assert (out / "astro.config.mjs").exists()
    assert (out / "wrangler.jsonc").exists()
    assert (out / "src/data/site.json").exists()
    assert (out / "src/pages/index.astro").exists()
    assert (out / "pwp-approval.json").exists()


def test_scaffold_astro_emdash_site_emits_rollback_command_in_seeded_metadata(tmp_path: Path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(_valkyrie_profile()))
    out = tmp_path / "site"

    scaffold_astro_emdash_site(profile, out, placeholder_only=False, overwrite=True)

    approval = json.loads((out / "pwp-approval.json").read_text())
    assert approval["rollback_command"].startswith(
        "PYTHONPATH=src python3 -m prismatic_web_plugin.approval rollback"
    )
    # The rollback command must target a real snapshot version (not an empty string).
    assert "--style-guide-version " + approval["style_guide_version"] in approval["rollback_command"]
    assert "--content-model-version " + approval["content_model_version"] in approval["rollback_command"]
