"""
Lifecycle workflow functions.

Each function represents one step in the model lifecycle:
  register → validate → review → approve → promote → retire
"""

from ..core.models import (
    ApprovalRecord,
    ApprovalStage,
    LifecycleState,
    ModelRecord,
    ValidationEvidence,
)
from ..core.registry import ModelRegistry
from ..core.lineage import LineageStore


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
) -> str:
    model = ModelRecord(
        name=name,
        version=version,
        owner=owner,
        artifact_uri=artifact_uri,
        tags=tags or {},
    )
    model_id = registry.register(model)
    lineage.record(model_id, experiment_id, dataset_version, parent_model_id)
    return model_id


def attach_validation_evidence(
    registry: ModelRegistry,
    model_id: str,
    evidence: list[ValidationEvidence],
) -> None:
    model = registry.get(model_id)
    model.validation_evidence.extend(evidence)
    # Move to IN_REVIEW only if all evidence passed
    if all(e.passed for e in model.validation_evidence):
        registry.update_state(model_id, LifecycleState.IN_REVIEW)
    else:
        registry.update_state(model_id, LifecycleState.REJECTED)


def approve_model(
    registry: ModelRegistry,
    model_id: str,
    stage: ApprovalStage,
    reviewer: str,
    notes: str = "",
) -> None:
    model = registry.get(model_id)
    if model.state not in (LifecycleState.IN_REVIEW, LifecycleState.CANDIDATE):
        raise ValueError(f"Model is in state '{model.state}', cannot approve")

    model.approvals.append(
        ApprovalRecord(stage=stage, approved=True, reviewer=reviewer, notes=notes)
    )

    approved_stages = {a.stage for a in model.approvals if a.approved}
    required = {ApprovalStage.VALIDATION, ApprovalStage.RISK_REVIEW, ApprovalStage.PRODUCTION_APPROVAL}
    if required.issubset(approved_stages):
        registry.update_state(model_id, LifecycleState.APPROVED)


def reject_model(
    registry: ModelRegistry,
    model_id: str,
    reviewer: str,
    stage: ApprovalStage,
    notes: str = "",
) -> None:
    model = registry.get(model_id)
    model.approvals.append(
        ApprovalRecord(stage=stage, approved=False, reviewer=reviewer, notes=notes)
    )
    registry.update_state(model_id, LifecycleState.REJECTED)


def promote_model(
    registry: ModelRegistry,
    model_id: str,
    environment: str,
) -> None:
    model = registry.get(model_id)
    if model.state != LifecycleState.APPROVED:
        raise ValueError(f"Model must be APPROVED before promotion, current state: '{model.state}'")
    model.deployed_to = environment
    registry.update_state(model_id, LifecycleState.DEPLOYED)


def retire_model(registry: ModelRegistry, model_id: str) -> None:
    model = registry.get(model_id)
    if model.state != LifecycleState.DEPLOYED:
        raise ValueError(f"Only DEPLOYED models can be retired, current state: '{model.state}'")
    registry.update_state(model_id, LifecycleState.RETIRED)
