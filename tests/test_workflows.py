"""
Tests covering the full model lifecycle:
  register → validate → approve (all 3 stages) → promote → retire
"""

import pytest
from src.core.models import ApprovalStage, LifecycleState, ValidationEvidence
from src.core.registry import ModelRegistry
from src.core.lineage import LineageStore
from src.pipelines.workflows import (
    approve_model,
    attach_validation_evidence,
    promote_model,
    register_model_candidate,
    reject_model,
    retire_model,
)


@pytest.fixture
def setup():
    return ModelRegistry(), LineageStore()


def _register(registry, lineage, name="fraud-detector", version="1.0"):
    return register_model_candidate(
        registry=registry,
        lineage=lineage,
        name=name,
        version=version,
        owner="ml-team",
        artifact_uri="s3://models/fraud-detector/1.0",
        experiment_id="exp-001",
        dataset_version="ds-2024-01",
    )


def _full_approve(registry, model_id):
    for stage in ApprovalStage:
        approve_model(registry, model_id, stage, reviewer="alice")


# --- Registration ---

def test_register_creates_candidate(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    model = registry.get(model_id)
    assert model.state == LifecycleState.CANDIDATE
    assert model.name == "fraud-detector"


def test_register_records_lineage(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    result = lineage.get_lineage(model_id)
    assert result["model_id"] == model_id
    assert result["ancestry"][0]["experiment_id"] == "exp-001"


# --- Validation ---

def test_passing_validation_moves_to_in_review(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    attach_validation_evidence(registry, model_id, [
        ValidationEvidence("accuracy", 0.95, passed=True),
        ValidationEvidence("f1", 0.91, passed=True),
    ])
    assert registry.get(model_id).state == LifecycleState.IN_REVIEW


def test_failing_validation_rejects_model(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    attach_validation_evidence(registry, model_id, [
        ValidationEvidence("accuracy", 0.60, passed=False),
    ])
    assert registry.get(model_id).state == LifecycleState.REJECTED


# --- Approval ---

def test_partial_approvals_stay_in_review(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    approve_model(registry, model_id, ApprovalStage.VALIDATION, reviewer="alice")
    assert registry.get(model_id).state != LifecycleState.APPROVED


def test_all_approvals_move_to_approved(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    _full_approve(registry, model_id)
    assert registry.get(model_id).state == LifecycleState.APPROVED


def test_rejection_moves_to_rejected(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    reject_model(registry, model_id, reviewer="bob", stage=ApprovalStage.RISK_REVIEW, notes="Too risky")
    assert registry.get(model_id).state == LifecycleState.REJECTED


# --- Promotion ---

def test_promote_approved_model(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    _full_approve(registry, model_id)
    promote_model(registry, model_id, environment="production")
    model = registry.get(model_id)
    assert model.state == LifecycleState.DEPLOYED
    assert model.deployed_to == "production"


def test_promote_unapproved_model_raises(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    with pytest.raises(ValueError, match="APPROVED"):
        promote_model(registry, model_id, environment="production")


# --- Retirement ---

def test_retire_deployed_model(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    _full_approve(registry, model_id)
    promote_model(registry, model_id, "production")
    retire_model(registry, model_id)
    assert registry.get(model_id).state == LifecycleState.RETIRED


def test_retire_non_deployed_model_raises(setup):
    registry, lineage = setup
    model_id = _register(registry, lineage)
    with pytest.raises(ValueError, match="DEPLOYED"):
        retire_model(registry, model_id)


# --- Registry queries ---

def test_list_models_by_state(setup):
    registry, lineage = setup
    _register(registry, lineage, name="model-a", version="1.0")
    id2 = _register(registry, lineage, name="model-b", version="1.0")
    _full_approve(registry, id2)
    approved = registry.list_models(state=LifecycleState.APPROVED)
    assert len(approved) == 1
    assert approved[0].name == "model-b"


# --- Lineage ancestry chain ---

def test_lineage_parent_chain(setup):
    registry, lineage = setup
    parent_id = _register(registry, lineage, name="model-v1", version="1.0")
    child_id = register_model_candidate(
        registry=registry,
        lineage=lineage,
        name="model-v2",
        version="2.0",
        owner="ml-team",
        artifact_uri="s3://models/v2",
        experiment_id="exp-002",
        dataset_version="ds-2024-02",
        parent_model_id=parent_id,
    )
    result = lineage.get_lineage(child_id)
    assert len(result["ancestry"]) == 2
    assert result["ancestry"][1]["model_id"] == parent_id
