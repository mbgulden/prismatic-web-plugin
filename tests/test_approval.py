"""Tests for the PWP approval/versioning/rollback module.

GRO-2505 (PWP-I13): Approval, versioning, and rollback for PWP site changes.

The acceptance criteria are:
1. Production deploy is blocked without approval.
2. Rollback restores a previous site/style guide/content model version.
3. Evidence is written automatically on publish.

These tests cover the library API. The CLI lives in `prismatic_web_plugin.approval.__main__`.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from prismatic_web_plugin.approval import (
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalState,
    DeployRecord,
    DeployTarget,
    RollbackResult,
    VersionSnapshot,
    approve_request,
    block_production_deploy,
    compute_content_model_version,
    compute_style_guide_version,
    list_deploy_history,
    propose_change,
    reject_request,
    rollback_to,
    write_evidence,
)

# ---------- fixtures -------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A clean PWP workspace with a single staged change."""
    ws = tmp_path / "pwp-workspace"
    (ws / "history").mkdir(parents=True)
    (ws / "evidence").mkdir(parents=True)

    style_guide = {"name": "Astro+EmDash", "primary": "#0c0d0f", "accent": "#c6a86b"}
    (ws / "style_guide.json").write_text(json.dumps(style_guide))

    content_model = {"schema": "page", "fields": ["title", "body", "hero"]}
    (ws / "content_model.json").write_text(json.dumps(content_model))

    (ws / "current_version.json").write_text(
        json.dumps(
            {
                "style_guide_version": compute_style_guide_version(style_guide),
                "content_model_version": compute_content_model_version(content_model),
            }
        )
    )
    return ws


@pytest.fixture
def change_profile() -> dict:
    return {
        "client_slug": "valkyrie-arms-training",
        "summary": "Update hero headline + accent color",
        "files": [
            "src/data/site.json",
            "src/pages/index.astro",
        ],
        "diff": {
            "src/data/site.json": {
                "before": {"homePage": {"headline": "Welcome"}},
                "after": {"homePage": {"headline": "Responsible training."}},
            }
        },
        "staging_preview_url": "https://staging-valkyrie.pwp.dev/",
    }


# ---------- version snapshots ---------------------------------------------


def test_compute_style_guide_version_is_stable_and_order_independent():
    sg_a = {"name": "Astro+EmDash", "primary": "#0c0d0f", "accent": "#c6a86b"}
    sg_b = {"accent": "#c6a86b", "primary": "#0c0d0f", "name": "Astro+EmDash"}

    assert compute_style_guide_version(sg_a) == compute_style_guide_version(sg_b)
    assert len(compute_style_guide_version(sg_a)) == 16  # truncated sha256


def test_compute_content_model_version_changes_on_field_added():
    cm_v1 = {"schema": "page", "fields": ["title", "body"]}
    cm_v2 = {"schema": "page", "fields": ["title", "body", "hero"]}

    assert compute_content_model_version(cm_v1) != compute_content_model_version(cm_v2)


def test_snapshot_captures_style_guide_and_content_model_versions(workspace):
    snapshot = VersionSnapshot.capture(
        workspace,
        style_guide=json.loads((workspace / "style_guide.json").read_text()),
        content_model=json.loads((workspace / "content_model.json").read_text()),
    )

    assert snapshot.style_guide_version
    assert snapshot.content_model_version
    assert snapshot.captured_at.endswith("Z")
    # ISO-8601 UTC
    datetime.fromisoformat(snapshot.captured_at.replace("Z", "+00:00"))


# ---------- approval request lifecycle ------------------------------------


def test_propose_change_creates_pending_request(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")

    assert request.state == ApprovalState.PENDING
    assert request.requested_by == "michael@gulden.io"
    assert request.client_slug == "valkyrie-arms-training"
    assert request.staging_preview_url == "https://staging-valkyrie.pwp.dev/"
    assert request.style_guide_version
    assert request.content_model_version

    # On-disk persistence
    on_disk = json.loads((workspace / "current_request.json").read_text())
    assert on_disk["id"] == request.id
    assert on_disk["state"] == ApprovalState.PENDING.value


def test_approve_request_transitions_state_and_records_metadata(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")

    approved = approve_request(
        workspace,
        request.id,
        approver="client@valkyrie.com",
        notes="Approved during weekly review",
    )

    assert approved.state == ApprovalState.APPROVED
    assert approved.approved_by == "client@valkyrie.com"
    assert approved.notes == "Approved during weekly review"
    assert approved.approved_at is not None


def test_reject_request_blocks_production_deploy(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    rejected = reject_request(
        workspace,
        request.id,
        approver="client@valkyrie.com",
        notes="Wrong headline copy",
    )

    assert rejected.state == ApprovalState.REJECTED

    # Production deploy must be blocked
    policy = ApprovalPolicy.default()
    block = block_production_deploy(rejected, policy)
    assert block.blocked is True
    assert "REJECTED" in block.reason or "rejected" in block.reason.lower()


def test_pending_request_blocks_production_deploy_by_default(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")

    policy = ApprovalPolicy.default()
    block = block_production_deploy(request, policy)
    assert block.blocked is True
    assert "approval" in block.reason.lower()


def test_approved_request_unblocks_production_deploy(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    approved = approve_request(
        workspace,
        request.id,
        approver="client@valkyrie.com",
        notes="Looks good",
    )

    policy = ApprovalPolicy.default()
    block = block_production_deploy(approved, policy)
    assert block.blocked is False


# ---------- deploy history + evidence --------------------------------------


def test_deploy_history_records_staging_and_production_with_evidence(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    approved = approve_request(workspace, request.id, approver="client@valkyrie.com", notes="ok")

    staging = DeployRecord.publish(
        workspace,
        request=approved,
        target=DeployTarget.STAGING,
        url="https://staging-valkyrie.pwp.dev/",
        actor="pwp-builder",
        evidence_path="evidence/GRO-2505-staging.md",
    )
    production = DeployRecord.publish(
        workspace,
        request=approved,
        target=DeployTarget.PRODUCTION,
        url="https://valkyriearmstraining.com/",
        actor="pwp-builder",
        evidence_path="evidence/GRO-2505-production.md",
    )

    history = list_deploy_history(workspace)
    assert [r.target for r in history] == [DeployTarget.PRODUCTION, DeployTarget.STAGING]
    assert staging.style_guide_version == approved.style_guide_version
    assert production.style_guide_version == approved.style_guide_version
    assert production.content_model_version == approved.content_model_version


def test_write_evidence_persists_okf_and_linear_metadata(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    approved = approve_request(workspace, request.id, approver="client@valkyrie.com", notes="ok")

    evidence = write_evidence(
        workspace,
        request=approved,
        deploy_target=DeployTarget.PRODUCTION,
        deploy_url="https://valkyriearmstraining.com/",
        linear_issue_id="GRO-2505",
        okf_paths=[
            "okf/projects/prismatic-web-plugin/decisions/2026-06-26-astro-emdash-pwp-standard.md"
        ],
    )

    assert evidence.path.exists()
    body = evidence.path.read_text()
    assert "GRO-2505" in body
    assert "https://valkyriearmstraining.com/" in body
    assert "Astro+EmDash" in body or "style_guide" in body.lower()
    assert "okf/projects/prismatic-web-plugin" in body


# ---------- rollback -------------------------------------------------------


def test_rollback_restores_previous_style_guide_and_content_model(workspace, change_profile):
    # Snapshot v1 (current on disk) — then "deploy" v2, then rollback.
    v1_style = json.loads((workspace / "style_guide.json").read_text())
    v1_model = json.loads((workspace / "content_model.json").read_text())
    snapshot_v1 = VersionSnapshot.capture(workspace, style_guide=v1_style, content_model=v1_model)
    snapshot_v1.persist(workspace, style_guide=v1_style, content_model=v1_model)

    # Mutate to v2 and deploy.
    v2_style = {**v1_style, "accent": "#ff5500"}
    v2_model = {**v1_model, "fields": v1_model["fields"] + ["cta"]}
    (workspace / "style_guide.json").write_text(json.dumps(v2_style))
    (workspace / "content_model.json").write_text(json.dumps(v2_model))
    (workspace / "current_version.json").write_text(
        json.dumps(
            {
                "style_guide_version": compute_style_guide_version(v2_style),
                "content_model_version": compute_content_model_version(v2_model),
            }
        )
    )

    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    approved = approve_request(workspace, request.id, approver="client@valkyrie.com", notes="ok")
    DeployRecord.publish(
        workspace,
        request=approved,
        target=DeployTarget.PRODUCTION,
        url="https://valkyriearmstraining.com/",
        actor="pwp-builder",
        evidence_path="evidence/GRO-2505-production.md",
    )

    # Roll back to v1.
    result = rollback_to(workspace, snapshot_v1.style_guide_version, snapshot_v1.content_model_version)

    assert isinstance(result, RollbackResult)
    assert result.success is True
    assert result.rolled_back_to.style_guide_version == snapshot_v1.style_guide_version

    # The on-disk style guide and content model must match v1.
    restored_style = json.loads((workspace / "style_guide.json").read_text())
    restored_model = json.loads((workspace / "content_model.json").read_text())
    assert restored_style == v1_style
    assert restored_model == v1_model


def test_rollback_records_a_history_entry(workspace, change_profile):
    snapshot_v1 = VersionSnapshot.capture(
        workspace,
        style_guide=json.loads((workspace / "style_guide.json").read_text()),
        content_model=json.loads((workspace / "content_model.json").read_text()),
    )
    v1_style = json.loads((workspace / "style_guide.json").read_text())
    v1_model = json.loads((workspace / "content_model.json").read_text())
    snapshot_v1.persist(workspace, style_guide=v1_style, content_model=v1_model)

    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    approved = approve_request(workspace, request.id, approver="client@valkyrie.com", notes="ok")
    DeployRecord.publish(
        workspace,
        request=approved,
        target=DeployTarget.PRODUCTION,
        url="https://valkyriearmstraining.com/",
        actor="pwp-builder",
        evidence_path="evidence/GRO-2505-production.md",
    )

    rollback_to(workspace, snapshot_v1.style_guide_version, snapshot_v1.content_model_version)

    history = list_deploy_history(workspace)
    kinds = [getattr(r, "kind", "deploy") for r in history]
    assert "rollback" in kinds


# ---------- policy ---------------------------------------------------------


def test_approval_policy_default_blocks_production_without_approval():
    policy = ApprovalPolicy.default()
    assert policy.require_approval_for == {DeployTarget.PRODUCTION}
    assert policy.allow_staging_without_approval is True


def test_block_production_deploy_message_includes_approver_when_missing(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    block = block_production_deploy(request, ApprovalPolicy.default())

    assert block.blocked is True
    assert request.id in block.reason
    assert "approved" in block.reason.lower()


# ---------- serialization roundtrip ---------------------------------------


def test_approval_request_roundtrips_through_json(workspace, change_profile):
    request = propose_change(workspace, change_profile, requested_by="michael@gulden.io")
    encoded = request.to_json()
    decoded = ApprovalRequest.from_json(encoded)

    assert decoded.id == request.id
    assert decoded.state == request.state
    assert decoded.client_slug == request.client_slug
    assert decoded.style_guide_version == request.style_guide_version
    assert decoded.content_model_version == request.content_model_version
    assert decoded.staging_preview_url == request.staging_preview_url
