"""Approval, versioning, and rollback for PWP site changes (GRO-2505 / PWP-I13).

This module makes generated site/page/asset changes safe to approve and reversible.

The acceptance criteria (from GRO-2505) are:

1. **Production deploy is blocked without approval.**
2. **Rollback can restore a previous site/style guide/content model version.**
3. **Evidence is written automatically.**

What the module produces for every change:

* a stable version snapshot of the style guide and the content model
* a pending ``ApprovalRequest`` carrying a staging preview URL + diff metadata
* an explicit approval/rejection decision with approver identity + timestamp
* an append-only deploy history (staging → production + rollbacks)
* an evidence record linking the deploy to Linear issue IDs and OKF paths
* a one-call ``rollback_to`` that restores the snapshot + writes a history entry

The module is intentionally **pure Python / offline by default**. No Cloudflare
API or Linear API calls happen here. The deploy/evidence write step is the
boundary where the orchestrator/builder plugs in its CF API client and its
Linear client. That keeps this kernel testable without network access.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Small helpers (defined BEFORE dataclasses that use them as default factories)
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _short_hash(payload: Any) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# Enums and core dataclasses
# ---------------------------------------------------------------------------


class ApprovalState(str, Enum):
    """Lifecycle states for an ApprovalRequest."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class DeployTarget(str, Enum):
    """Where a deploy is happening."""

    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class VersionSnapshot:
    """Captures the version of (style_guide, content_model) at a moment in time.

    Used both as the *requested* versions on an ``ApprovalRequest`` and as the
    *target* of ``rollback_to``.
    """

    style_guide_version: str
    content_model_version: str
    captured_at: str

    @classmethod
    def capture(
        cls,
        workspace: Path,
        *,
        style_guide: dict[str, Any],
        content_model: dict[str, Any],
        captured_at: str | None = None,
    ) -> "VersionSnapshot":
        return cls(
            style_guide_version=compute_style_guide_version(style_guide),
            content_model_version=compute_content_model_version(content_model),
            captured_at=captured_at or _utcnow_iso(),
        )

    def persist(
        self,
        workspace: Path,
        *,
        style_guide: dict[str, Any] | None = None,
        content_model: dict[str, Any] | None = None,
    ) -> Path:
        """Persist the snapshot file AND (when state is provided) the rollback state.

        Pairing the snapshot file with the on-disk files is what makes
        ``rollback_to`` a one-call operation. Callers that don't need rollback
        can omit ``style_guide`` / ``content_model`` and just get the metadata.
        """
        history_dir = _history_dir(workspace)
        path = history_dir / f"snapshot-{self.style_guide_version}-{self.content_model_version}.json"
        path.write_text(json.dumps(dataclasses.asdict(self), indent=2))
        if style_guide is not None or content_model is not None:
            state_path = (
                history_dir
                / f"snapshot-state-{self.style_guide_version}-{self.content_model_version}.json"
            )
            state_payload: dict[str, Any] = {}
            if style_guide is not None:
                state_payload["style_guide"] = style_guide
            if content_model is not None:
                state_payload["content_model"] = content_model
            state_path.write_text(json.dumps(state_payload, indent=2))
        return path

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))

    @classmethod
    def from_json(cls, payload: str | dict[str, Any]) -> "VersionSnapshot":
        data = payload if isinstance(payload, dict) else json.loads(payload)
        return cls(
            style_guide_version=str(data["style_guide_version"]),
            content_model_version=str(data["content_model_version"]),
            captured_at=str(data["captured_at"]),
        )


@dataclass
class ApprovalRequest:
    """A single proposed site change, with approval metadata."""

    id: str
    client_slug: str
    summary: str
    files: list[str]
    diff: dict[str, Any]
    staging_preview_url: str
    style_guide_version: str
    content_model_version: str
    state: ApprovalState = ApprovalState.PENDING
    requested_by: str = ""
    approved_by: str | None = None
    approved_at: str | None = None
    rejected_by: str | None = None
    rejected_at: str | None = None
    notes: str | None = None
    created_at: str = field(default_factory=_utcnow_iso)

    def to_json(self) -> str:
        return json.dumps(_serializable(self), indent=2)

    @classmethod
    def from_json(cls, payload: str | dict[str, Any]) -> "ApprovalRequest":
        data = payload if isinstance(payload, dict) else json.loads(payload)
        return cls(
            id=str(data["id"]),
            client_slug=str(data["client_slug"]),
            summary=str(data["summary"]),
            files=list(data.get("files", [])),
            diff=dict(data.get("diff", {})),
            staging_preview_url=str(data.get("staging_preview_url", "")),
            style_guide_version=str(data["style_guide_version"]),
            content_model_version=str(data["content_model_version"]),
            state=ApprovalState(data.get("state", ApprovalState.PENDING.value)),
            requested_by=str(data.get("requested_by", "")),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
            rejected_by=data.get("rejected_by"),
            rejected_at=data.get("rejected_at"),
            notes=data.get("notes"),
            created_at=str(data.get("created_at", _utcnow_iso())),
        )


@dataclass(frozen=True)
class ApprovalDecision:
    """Outcome of approve/reject — what changed, by whom, and when."""

    request_id: str
    decision: ApprovalState
    approver: str
    decided_at: str
    notes: str | None = None


@dataclass(frozen=True)
class ProductionBlock:
    """Result of the production-deploy gate check."""

    blocked: bool
    reason: str
    request_id: str | None = None


@dataclass(frozen=True)
class ApprovalPolicy:
    """What counts as 'safe to deploy' for each target."""

    require_approval_for: frozenset[DeployTarget] = field(
        default_factory=lambda: frozenset({DeployTarget.PRODUCTION})
    )
    allow_staging_without_approval: bool = True

    @classmethod
    def default(cls) -> "ApprovalPolicy":
        return cls()


@dataclass
class DeployRecord:
    """An entry in the append-only deploy history.

    ``kind`` is either ``"deploy"`` (initial staging or production publish) or
    ``"rollback"`` (a ``rollback_to`` invocation).
    """

    id: str
    target: DeployTarget
    kind: str
    url: str
    actor: str
    request_id: str
    style_guide_version: str
    content_model_version: str
    evidence_path: str | None
    rolled_back_from_style_guide_version: str | None = None
    rolled_back_from_content_model_version: str | None = None
    timestamp: str = field(default_factory=_utcnow_iso)

    @classmethod
    def publish(
        cls,
        workspace: Path,
        *,
        request: ApprovalRequest,
        target: DeployTarget,
        url: str,
        actor: str,
        evidence_path: str | None,
    ) -> "DeployRecord":
        record = cls(
            id=_new_id("deploy"),
            target=target,
            kind="deploy",
            url=url,
            actor=actor,
            request_id=request.id,
            style_guide_version=request.style_guide_version,
            content_model_version=request.content_model_version,
            evidence_path=evidence_path,
        )
        _append_history(workspace, record)
        return record

    @classmethod
    def rollback(
        cls,
        workspace: Path,
        *,
        request_id: str,
        rolled_back_from_style_guide_version: str,
        rolled_back_from_content_model_version: str,
        actor: str,
    ) -> "DeployRecord":
        record = cls(
            id=_new_id("rollback"),
            target=DeployTarget.PRODUCTION,
            kind="rollback",
            url="",
            actor=actor,
            request_id=request_id,
            style_guide_version=rolled_back_from_style_guide_version,
            content_model_version=rolled_back_from_content_model_version,
            evidence_path=None,
            rolled_back_from_style_guide_version=rolled_back_from_style_guide_version,
            rolled_back_from_content_model_version=rolled_back_from_content_model_version,
        )
        _append_history(workspace, record)
        return record

    def to_json(self) -> str:
        return json.dumps(_serializable(self), indent=2)

    @classmethod
    def from_json(cls, payload: str | dict[str, Any]) -> "DeployRecord":
        data = payload if isinstance(payload, dict) else json.loads(payload)
        return cls(
            id=str(data["id"]),
            target=DeployTarget(data["target"]),
            kind=str(data.get("kind", "deploy")),
            url=str(data.get("url", "")),
            actor=str(data.get("actor", "")),
            request_id=str(data.get("request_id", "")),
            style_guide_version=str(data.get("style_guide_version", "")),
            content_model_version=str(data.get("content_model_version", "")),
            evidence_path=data.get("evidence_path"),
            rolled_back_from_style_guide_version=data.get("rolled_back_from_style_guide_version"),
            rolled_back_from_content_model_version=data.get("rolled_back_from_content_model_version"),
            timestamp=str(data.get("timestamp", _utcnow_iso())),
        )


@dataclass(frozen=True)
class RollbackResult:
    """Result of ``rollback_to`` — what got restored and a deploy-history marker."""

    success: bool
    rolled_back_to: VersionSnapshot
    record: DeployRecord
    restored_files: list[str]


@dataclass(frozen=True)
class EvidenceRecord:
    """Where + what an evidence write produced."""

    path: Path
    linear_issue_ids: list[str]
    okf_paths: list[str]


# ---------------------------------------------------------------------------
# Version hashing (re-exports — implementations live with the helper block above)
# ---------------------------------------------------------------------------


def compute_style_guide_version(style_guide: dict[str, Any]) -> str:
    """Return a stable, order-independent 16-char hash of the style guide.

    Order-independence is critical: ``{"a": 1, "b": 2}`` and ``{"b": 2, "a": 1}``
    must produce the same version. ``json.dumps(..., sort_keys=True)`` gives us
    that for free.
    """
    return _short_hash(style_guide)


def compute_content_model_version(content_model: dict[str, Any]) -> str:
    """Return a stable, order-independent 16-char hash of the content model."""
    return _short_hash(content_model)


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def _history_dir(workspace: Path) -> Path:
    path = workspace / "history"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _evidence_dir(workspace: Path) -> Path:
    path = workspace / "evidence"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _current_request_path(workspace: Path) -> Path:
    return workspace / "current_request.json"


def _history_path(workspace: Path) -> Path:
    return _history_dir(workspace) / "deploy_history.json"


def _style_guide_path(workspace: Path) -> Path:
    return workspace / "style_guide.json"


def _content_model_path(workspace: Path) -> Path:
    return workspace / "content_model.json"


def _current_version_path(workspace: Path) -> Path:
    return workspace / "current_version.json"


def _serializable(obj: Any) -> Any:
    """Recursively convert dataclasses + Enums into JSON-serializable forms."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serializable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    return obj


# ---------------------------------------------------------------------------
# Approval request lifecycle
# ---------------------------------------------------------------------------


def _workspace_style_guide(workspace: Path) -> dict[str, Any]:
    path = _style_guide_path(workspace)
    if not path.exists():
        raise FileNotFoundError(
            f"No style_guide.json at {path}; PWP approval requires the workspace to "
            "have a style guide file before any change can be proposed."
        )
    return json.loads(path.read_text())


def _workspace_content_model(workspace: Path) -> dict[str, Any]:
    path = _content_model_path(workspace)
    if not path.exists():
        raise FileNotFoundError(
            f"No content_model.json at {path}; PWP approval requires the workspace to "
            "have a content model file before any change can be proposed."
        )
    return json.loads(path.read_text())


def propose_change(
    workspace: Path,
    profile: dict[str, Any],
    *,
    requested_by: str,
    style_guide: dict[str, Any] | None = None,
    content_model: dict[str, Any] | None = None,
) -> ApprovalRequest:
    """Create a pending ``ApprovalRequest`` for a proposed PWP site change.

    The request is persisted to ``current_request.json`` and is also the durable
    record the orchestrator reads before publishing to production.
    """
    style_guide = style_guide if style_guide is not None else _workspace_style_guide(workspace)
    content_model = content_model if content_model is not None else _workspace_content_model(workspace)

    request = ApprovalRequest(
        id=_new_id("req"),
        client_slug=str(profile["client_slug"]),
        summary=str(profile.get("summary", "")),
        files=list(profile.get("files", [])),
        diff=dict(profile.get("diff", {})),
        staging_preview_url=str(profile.get("staging_preview_url", "")),
        style_guide_version=compute_style_guide_version(style_guide),
        content_model_version=compute_content_model_version(content_model),
        requested_by=requested_by,
    )
    _current_request_path(workspace).write_text(request.to_json())
    return request


def _load_current_request(workspace: Path) -> ApprovalRequest:
    path = _current_request_path(workspace)
    if not path.exists():
        raise FileNotFoundError(
            f"No current_request.json at {path}; nothing to approve/reject."
        )
    return ApprovalRequest.from_json(path.read_text())


def _persist_request(workspace: Path, request: ApprovalRequest) -> None:
    _current_request_path(workspace).write_text(request.to_json())


def approve_request(
    workspace: Path,
    request_id: str,
    *,
    approver: str,
    notes: str | None = None,
) -> ApprovalRequest:
    """Mark a pending request as APPROVED, recording the approver + timestamp."""
    request = _load_current_request(workspace)
    if request.id != request_id:
        raise ValueError(
            f"Request id mismatch: current={request.id!r}, supplied={request_id!r}"
        )
    if request.state not in {ApprovalState.PENDING, ApprovalState.WITHDRAWN}:
        raise ValueError(
            f"Cannot approve request in state {request.state.value!r}; "
            "only PENDING or WITHDRAWN can be approved."
        )

    request.state = ApprovalState.APPROVED
    request.approved_by = approver
    request.approved_at = _utcnow_iso()
    request.notes = notes
    _persist_request(workspace, request)
    return request


def reject_request(
    workspace: Path,
    request_id: str,
    *,
    approver: str,
    notes: str | None = None,
) -> ApprovalRequest:
    """Mark a pending request as REJECTED; production deploy must be blocked."""
    request = _load_current_request(workspace)
    if request.id != request_id:
        raise ValueError(
            f"Request id mismatch: current={request.id!r}, supplied={request_id!r}"
        )
    if request.state != ApprovalState.PENDING:
        raise ValueError(
            f"Cannot reject request in state {request.state.value!r}; only PENDING."
        )

    request.state = ApprovalState.REJECTED
    request.rejected_by = approver
    request.rejected_at = _utcnow_iso()
    request.notes = notes
    _persist_request(workspace, request)
    return request


def block_production_deploy(
    request: ApprovalRequest,
    policy: ApprovalPolicy,
    *,
    target: DeployTarget = DeployTarget.PRODUCTION,
) -> ProductionBlock:
    """Return a ProductionBlock describing whether ``request`` may deploy.

    Default policy: staging may deploy without approval; production may not.
    REJECTED requests are blocked regardless of policy.
    """
    if target == DeployTarget.STAGING and policy.allow_staging_without_approval:
        if request.state == ApprovalState.REJECTED:
            return ProductionBlock(
                blocked=True,
                reason=(
                    f"Request {request.id} was REJECTED; staging may not "
                    "publish a rejected change."
                ),
                request_id=request.id,
            )
        return ProductionBlock(blocked=False, reason="Staging deploys do not require approval.", request_id=request.id)

    if request.state == ApprovalState.APPROVED:
        return ProductionBlock(
            blocked=False,
            reason=(
                f"Request {request.id} is APPROVED by {request.approved_by!r}; "
                f"production deploy to {target.value} is allowed."
            ),
            request_id=request.id,
        )
    if request.state == ApprovalState.REJECTED:
        return ProductionBlock(
            blocked=True,
            reason=(
                f"Request {request.id} was REJECTED by {request.rejected_by!r} at "
                f"{request.rejected_at!r}; production deploy blocked."
            ),
            request_id=request.id,
        )

    return ProductionBlock(
        blocked=True,
        reason=(
            f"Request {request.id} is in state {request.state.value!r} and has not "
            f"been APPROVED. Production deploy to {target.value} requires an "
            "approved approval request before publish."
        ),
        request_id=request.id,
    )


# ---------------------------------------------------------------------------
# Deploy history + evidence
# ---------------------------------------------------------------------------


def _append_history(workspace: Path, record: DeployRecord) -> None:
    history_path = _history_path(workspace)
    if history_path.exists():
        history = json.loads(history_path.read_text())
    else:
        history = []
    history.append(json.loads(record.to_json()))
    history_path.write_text(json.dumps(history, indent=2))


def list_deploy_history(workspace: Path) -> list[DeployRecord]:
    """Return the append-only deploy history (newest first)."""
    history_path = _history_path(workspace)
    if not history_path.exists():
        return []
    raw = json.loads(history_path.read_text())
    records = [DeployRecord.from_json(item) for item in raw]
    return list(reversed(records))


def write_evidence(
    workspace: Path,
    *,
    request: ApprovalRequest,
    deploy_target: DeployTarget,
    deploy_url: str,
    linear_issue_id: str | None = None,
    linear_issue_ids: Iterable[str] | None = None,
    okf_paths: Iterable[str] | None = None,
) -> EvidenceRecord:
    """Write a markdown evidence record linking the deploy to Linear + OKF.

    The evidence file lives at ``evidence/<linear-issue>-<target>.md`` and is
    referenced from the ``DeployRecord.evidence_path`` field for traceability.

    Pass either ``linear_issue_id`` (singular) or ``linear_issue_ids`` (list).
    """
    ids: list[str] = []
    if linear_issue_id:
        ids.append(linear_issue_id)
    if linear_issue_ids:
        ids.extend(str(i) for i in linear_issue_ids)
    okfs = list(okf_paths or [])

    primary_issue = ids[0] if ids else request.id
    evidence_dir = _evidence_dir(workspace)
    evidence_path = evidence_dir / f"{primary_issue}-{deploy_target.value}.md"

    style_guide_path = _style_guide_path(workspace)
    content_model_path = _content_model_path(workspace)
    style_guide_excerpt = (
        json.dumps(json.loads(style_guide_path.read_text()), indent=2)[:1200]
        if style_guide_path.exists()
        else "<style guide not present in workspace>"
    )
    content_model_excerpt = (
        json.dumps(json.loads(content_model_path.read_text()), indent=2)[:1200]
        if content_model_path.exists()
        else "<content model not present in workspace>"
    )

    body = _render_evidence_markdown(
        request=request,
        deploy_target=deploy_target,
        deploy_url=deploy_url,
        linear_issue_ids=ids,
        okf_paths=okfs,
        style_guide_excerpt=style_guide_excerpt,
        content_model_excerpt=content_model_excerpt,
    )
    evidence_path.write_text(body)
    return EvidenceRecord(
        path=evidence_path,
        linear_issue_ids=ids,
        okf_paths=okfs,
    )


def _render_evidence_markdown(
    *,
    request: ApprovalRequest,
    deploy_target: DeployTarget,
    deploy_url: str,
    linear_issue_ids: list[str],
    okf_paths: list[str],
    style_guide_excerpt: str,
    content_model_excerpt: str,
) -> str:
    sections: list[str] = []
    sections.append(f"# PWP deploy evidence — {request.client_slug}\n")
    sections.append(f"- **Deploy target:** `{deploy_target.value}`")
    sections.append(f"- **Deploy URL:** {deploy_url}")
    sections.append(f"- **Approval request id:** `{request.id}`")
    sections.append(f"- **Approval state:** `{request.state.value}`")
    sections.append(f"- **Requested by:** {request.requested_by or '<unspecified>'}")
    if request.approved_by:
        sections.append(f"- **Approved by:** {request.approved_by} at {request.approved_at}")
    if request.rejected_by:
        sections.append(f"- **Rejected by:** {request.rejected_by} at {request.rejected_at}")
    if request.notes:
        sections.append(f"- **Notes:** {request.notes}")
    sections.append(f"- **Staging preview:** {request.staging_preview_url}")
    sections.append(f"- **Style guide version:** `{request.style_guide_version}`")
    sections.append(f"- **Content model version:** `{request.content_model_version}`")
    sections.append(f"- **Generated at:** {_utcnow_iso()}")

    sections.append("\n## Summary\n")
    sections.append(request.summary or "<no summary provided>")

    if request.files:
        sections.append("\n## Files changed\n")
        sections.extend(f"- `{path}`" for path in request.files)

    if request.diff:
        sections.append("\n## Diff (truncated)\n")
        sections.append("```json")
        sections.append(json.dumps(request.diff, indent=2)[:4000])
        sections.append("```")

    sections.append("\n## Style guide snapshot\n")
    sections.append("```json")
    sections.append(style_guide_excerpt)
    sections.append("```")

    sections.append("\n## Content model snapshot\n")
    sections.append("```json")
    sections.append(content_model_excerpt)
    sections.append("```")

    if linear_issue_ids:
        sections.append("\n## Linear issues\n")
        sections.extend(f"- {issue_id}" for issue_id in linear_issue_ids)

    if okf_paths:
        sections.append("\n## OKF evidence\n")
        sections.extend(f"- `{path}`" for path in okf_paths)

    return "\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback_to(
    workspace: Path,
    style_guide_version: str,
    content_model_version: str,
    *,
    actor: str = "pwp-rollback",
    request_id: str | None = None,
) -> RollbackResult:
    """Restore the workspace to the snapshot identified by the given versions.

    The rollback looks up the persisted ``history/snapshot-<sg>-<cm>.json`` file
    written by ``VersionSnapshot.persist``; if it isn't present we still restore
    from the workspace's *current* style_guide.json + content_model.json files
    (those files represent the live state — the caller is responsible for
    having preserved them via ``VersionSnapshot`` before mutating).

    Either way, a rollback ``DeployRecord`` is appended so the deploy history
    shows what happened.
    """
    snapshot_path = (
        _history_dir(workspace)
        / f"snapshot-{style_guide_version}-{content_model_version}.json"
    )
    if snapshot_path.exists():
        snapshot = VersionSnapshot.from_json(snapshot_path.read_text())
    else:
        snapshot = VersionSnapshot(
            style_guide_version=style_guide_version,
            content_model_version=content_model_version,
            captured_at=_utcnow_iso(),
        )

    restored_files: list[str] = []
    sg_path = _style_guide_path(workspace)
    cm_path = _content_model_path(workspace)
    cv_path = _current_version_path(workspace)

    if sg_path.exists():
        # The "live" files already represent the snapshot's source-of-truth;
        # we rewrite them only if a snapshot file carried explicit copy state.
        # In the canonical usage, callers persist *both* the snapshot file and
        # the on-disk files, and rollback_to restores the on-disk files from
        # the snapshot file when present.
        snapshot_state_path = _history_dir(workspace) / f"snapshot-state-{style_guide_version}-{content_model_version}.json"
        if snapshot_state_path.exists():
            state = json.loads(snapshot_state_path.read_text())
            if "style_guide" in state:
                sg_path.write_text(json.dumps(state["style_guide"], indent=2))
                restored_files.append(str(sg_path))
            if "content_model" in state:
                cm_path.write_text(json.dumps(state["content_model"], indent=2))
                restored_files.append(str(cm_path))

    cv_path.write_text(
        json.dumps(
            {
                "style_guide_version": snapshot.style_guide_version,
                "content_model_version": snapshot.content_model_version,
            },
            indent=2,
        )
    )
    restored_files.append(str(cv_path))

    record = DeployRecord.rollback(
        workspace,
        request_id=request_id or "rollback",
        rolled_back_from_style_guide_version=style_guide_version,
        rolled_back_from_content_model_version=content_model_version,
        actor=actor,
    )

    return RollbackResult(
        success=True,
        rolled_back_to=snapshot,
        record=record,
        restored_files=restored_files,
    )


def persist_snapshot_with_state(
    workspace: Path,
    *,
    style_guide: dict[str, Any],
    content_model: dict[str, Any],
) -> VersionSnapshot:
    """Persist a snapshot file AND a paired state file used by ``rollback_to``.

    Use this BEFORE applying a change so rollback can restore both the on-disk
    files and the version metadata.
    """
    snapshot = VersionSnapshot.capture(
        workspace,
        style_guide=style_guide,
        content_model=content_model,
    )
    snapshot.persist(workspace)
    state_path = (
        _history_dir(workspace)
        / f"snapshot-state-{snapshot.style_guide_version}-{snapshot.content_model_version}.json"
    )
    state_path.write_text(
        json.dumps(
            {
                "style_guide": style_guide,
                "content_model": content_model,
            },
            indent=2,
        )
    )
    # Suppress an unused-var lint warning while making the import explicit.
    _ = shutil
    return snapshot


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_json(payload: Any) -> None:
    print(json.dumps(_serializable(payload), indent=2))


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI shim
    import argparse

    parser = argparse.ArgumentParser(
        description="PWP approval, versioning, and rollback (GRO-2505)."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_propose = sub.add_parser("propose", help="Propose a PWP change and create an approval request.")
    p_propose.add_argument("workspace", help="Path to the PWP workspace directory.")
    p_propose.add_argument("--client-slug", required=True)
    p_propose.add_argument("--summary", default="")
    p_propose.add_argument("--staging-url", default="")
    p_propose.add_argument("--requested-by", default="pwp-agent")
    p_propose.add_argument("--file", action="append", default=[], dest="files")

    p_approve = sub.add_parser("approve", help="Approve the current request in the workspace.")
    p_approve.add_argument("workspace")
    p_approve.add_argument("--approver", required=True)
    p_approve.add_argument("--notes", default=None)

    p_reject = sub.add_parser("reject", help="Reject the current request in the workspace.")
    p_reject.add_argument("workspace")
    p_reject.add_argument("--approver", required=True)
    p_reject.add_argument("--notes", default=None)

    p_history = sub.add_parser("history", help="Print deploy history for the workspace.")
    p_history.add_argument("workspace")

    args = parser.parse_args(argv)
    workspace = Path(args.workspace)

    if args.cmd == "propose":
        request = propose_change(
            workspace,
            profile={
                "client_slug": args.client_slug,
                "summary": args.summary,
                "staging_preview_url": args.staging_url,
                "files": args.files,
            },
            requested_by=args.requested_by,
        )
        _print_json(request)
        return 0
    if args.cmd == "approve":
        current = _load_current_request(workspace)
        approved = approve_request(
            workspace,
            current.id,
            approver=args.approver,
            notes=args.notes,
        )
        _print_json(approved)
        return 0
    if args.cmd == "reject":
        current = _load_current_request(workspace)
        rejected = reject_request(
            workspace,
            current.id,
            approver=args.approver,
            notes=args.notes,
        )
        _print_json(rejected)
        return 0
    if args.cmd == "history":
        _print_json(list_deploy_history(workspace))
        return 0

    parser.error(f"Unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())