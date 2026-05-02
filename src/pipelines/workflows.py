"""
Lifecycle workflow functions.

Each function represents one step in the model lifecycle:
  register → validate → approve (all stages) → promote → retire

All registry backends (memory, SQL, MLflow) work here — any object that
implements register / get / list_models / save is accepted.

Pass an AuditLog instance to record every transition for compliance.
"""

from typing import Optional

from ..core.models import (
    ApprovalRecord,
    ApprovalStage,
    LifecycleState,
    ModelCard,
    ModelRecord,
    ValidationEvidence,
)
from ..core.registry import ModelRegistry
from ..core.lineage import LineageStore
from ..core.audit import AuditEvent, AuditLog

_DEFAULT_REQUIRED_STAGES = {
    ApprovalStage.VALIDATION,
    ApprovalStage.RISK_REVIEW,
    ApprovalStage.PRODUCTION_APPROVAL,
}


def register_model_candidate(
    registry: ModelRegistry,
    lineage: LineageStore,
    name: str,
    version: str,
    owner: str,
    artifact_uri: str,
    experiment_id: str,
    dataset_version: str,
    parent_model_id: str | None = None,
    tags: dict[str, str] | None = None,
    audit_log: Optional[AuditLog] = None,
) -> str:
    # Prevent duplicate name+version registrations
    if any(m.name == name and m.version == version for m in registry.list_models()):
        raise ValueError(f"Model '{name}' version '{version}' is already registered")

    model = ModelRecord(
        name=name,
        version=version,
        owner=owner,
        artifact_uri=artifact_uri,
        tags=tags or {},
    )
    model_id = registry.register(model)
    lineage.record(model_id, experiment_id, dataset_version, parent_model_id)

    if audit_log:
        audit_log.record(AuditEvent(
            model_id=model_id,
            event_type="registered",
            actor=owner,
            to_state=LifecycleState.CANDIDATE.value,
            details={"name": name, "version": version, "artifact_uri": artifact_uri},
        ))
    return model_id


def attach_validation_evidence(
    registry: ModelRegistry,
    model_id: str,
    evidence: list[ValidationEvidence],
    audit_log: Optional[AuditLog] = None,
) -> None:
    model = registry.get(model_id)
    old_state = model.state
    model.validation_evidence.extend(evidence)
    model.state = (
        LifecycleState.IN_REVIEW
        if all(e.passed for e in model.validation_evidence)
        else LifecycleState.REJECTED
    )
    registry.save(model)

    if audit_log:
        audit_log.record(AuditEvent(
            model_id=model_id,
            event_type="evidence_attached",
            actor="system",
            from_state=old_state.value,
            to_state=model.state.value,
            details={
                "evidence_count": len(evidence),
                "all_passed": model.state == LifecycleState.IN_REVIEW,
            },
        ))


def approve_model(
    registry: ModelRegistry,
    model_id: str,
    stage: ApprovalStage,
    reviewer: str,
    notes: str = "",
    audit_log: Optional[AuditLog] = None,
    required_stages: Optional[set[ApprovalStage]] = None,
) -> None:
    model = registry.get(model_id)
    if model.state not in (LifecycleState.IN_REVIEW, LifecycleState.CANDIDATE):
        raise ValueError(f"Model is in state '{model.state}', cannot approve")

    old_state = model.state
    model.approvals.append(
        ApprovalRecord(stage=stage, approved=True, reviewer=reviewer, notes=notes)
    )

    _required = required_stages if required_stages is not None else _DEFAULT_REQUIRED_STAGES
    approved_stages = {a.stage for a in model.approvals if a.approved}
    if _required.issubset(approved_stages):
        model.state = LifecycleState.APPROVED

    registry.save(model)

    if audit_log:
        audit_log.record(AuditEvent(
            model_id=model_id,
            event_type="stage_approved",
            actor=reviewer,
            from_state=old_state.value,
            to_state=model.state.value,
            details={"stage": stage.value, "notes": notes},
        ))


def reject_model(
    registry: ModelRegistry,
    model_id: str,
    reviewer: str,
    stage: ApprovalStage,
    notes: str = "",
    audit_log: Optional[AuditLog] = None,
) -> None:
    model = registry.get(model_id)
    old_state = model.state
    model.approvals.append(
        ApprovalRecord(stage=stage, approved=False, reviewer=reviewer, notes=notes)
    )
    model.state = LifecycleState.REJECTED
    registry.save(model)

    if audit_log:
        audit_log.record(AuditEvent(
            model_id=model_id,
            event_type="stage_rejected",
            actor=reviewer,
            from_state=old_state.value,
            to_state=LifecycleState.REJECTED.value,
            details={"stage": stage.value, "notes": notes},
        ))


def promote_model(
    registry: ModelRegistry,
    model_id: str,
    environment: str,
    actor: str = "system",
    audit_log: Optional[AuditLog] = None,
) -> None:
    model = registry.get(model_id)
    if model.state != LifecycleState.APPROVED:
        raise ValueError(f"Model must be APPROVED before promotion, current state: '{model.state}'")
    model.deployed_to = environment
    model.state = LifecycleState.DEPLOYED
    registry.save(model)

    if audit_log:
        audit_log.record(AuditEvent(
            model_id=model_id,
            event_type="promoted",
            actor=actor,
            from_state=LifecycleState.APPROVED.value,
            to_state=LifecycleState.DEPLOYED.value,
            details={"environment": environment},
        ))


def retire_model(
    registry: ModelRegistry,
    model_id: str,
    actor: str = "system",
    audit_log: Optional[AuditLog] = None,
) -> None:
    model = registry.get(model_id)
    if model.state != LifecycleState.DEPLOYED:
        raise ValueError(f"Only DEPLOYED models can be retired, current state: '{model.state}'")
    model.state = LifecycleState.RETIRED
    registry.save(model)

    if audit_log:
        audit_log.record(AuditEvent(
            model_id=model_id,
            event_type="retired",
            actor=actor,
            from_state=LifecycleState.DEPLOYED.value,
            to_state=LifecycleState.RETIRED.value,
            details={},
        ))


def attach_model_card(
    registry: ModelRegistry,
    model_id: str,
    card: ModelCard,
    actor: str = "system",
    audit_log: Optional[AuditLog] = None,
) -> None:
    model = registry.get(model_id)
    model.model_card = card
    registry.save(model)

    if audit_log:
        audit_log.record(AuditEvent(
            model_id=model_id,
            event_type="model_card_attached",
            actor=actor,
            details={"intended_use": card.intended_use},
        ))
