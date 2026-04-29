"""
Runs the full model lifecycle against all three registry backends:
  memory (dict), sql (SQLite), mlflow (tracking server)
"""

import pytest

from src.core.models import ApprovalStage, LifecycleState, ValidationEvidence
from src.core.lineage import LineageStore
from src.core.registry import ModelRegistry
from src.core.registry_sql import SQLModelRegistry
from src.core.registry_mlflow import MLflowModelRegistry
from src.pipelines.workflows import (
    approve_model,
    attach_validation_evidence,
    promote_model,
    register_model_candidate,
    reject_model,
    retire_model,
)


@pytest.fixture(params=["memory", "sql", "mlflow"])
def registry(request, tmp_path):
    if request.param == "memory":
        return ModelRegistry()
    if request.param == "sql":
        return SQLModelRegistry(f"sqlite:///{tmp_path}/test.db")
    return MLflowModelRegistry(str(tmp_path / "mlruns"))


@pytest.fixture
def lineage():
    return LineageStore()


def _register(registry, lineage):
    return register_model_candidate(
        registry=registry,
        lineage=lineage,
        name="churn-model",
        version="1.0",
        owner="ml-team",
        artifact_uri="s3://models/churn/1.0",
        experiment_id="exp-99",
        dataset_version="ds-v1",
    )


def _full_approve(registry, model_id):
    for stage in ApprovalStage:
        approve_model(registry, model_id, stage, reviewer="alice")


def test_register_is_candidate(registry, lineage):
    model_id = _register(registry, lineage)
    assert registry.get(model_id).state == LifecycleState.CANDIDATE


def test_passing_evidence_moves_to_review(registry, lineage):
    model_id = _register(registry, lineage)
    attach_validation_evidence(registry, model_id, [
        ValidationEvidence("accuracy", 0.95, passed=True),
    ])
    assert registry.get(model_id).state == LifecycleState.IN_REVIEW


def test_failing_evidence_rejects(registry, lineage):
    model_id = _register(registry, lineage)
    attach_validation_evidence(registry, model_id, [
        ValidationEvidence("accuracy", 0.55, passed=False),
    ])
    assert registry.get(model_id).state == LifecycleState.REJECTED


def test_evidence_persists(registry, lineage):
    model_id = _register(registry, lineage)
    attach_validation_evidence(registry, model_id, [
        ValidationEvidence("f1", 0.88, passed=True),
    ])
    assert len(registry.get(model_id).validation_evidence) == 1


def test_partial_approvals_not_approved(registry, lineage):
    model_id = _register(registry, lineage)
    approve_model(registry, model_id, ApprovalStage.VALIDATION, reviewer="alice")
    assert registry.get(model_id).state != LifecycleState.APPROVED


def test_full_approval_cycle(registry, lineage):
    model_id = _register(registry, lineage)
    _full_approve(registry, model_id)
    assert registry.get(model_id).state == LifecycleState.APPROVED


def test_approvals_persist(registry, lineage):
    model_id = _register(registry, lineage)
    approve_model(registry, model_id, ApprovalStage.VALIDATION, reviewer="alice")
    assert len(registry.get(model_id).approvals) == 1


def test_rejection_persists(registry, lineage):
    model_id = _register(registry, lineage)
    reject_model(registry, model_id, reviewer="bob", stage=ApprovalStage.RISK_REVIEW)
    model = registry.get(model_id)
    assert model.state == LifecycleState.REJECTED
    assert len(model.approvals) == 1


def test_promote_after_full_approval(registry, lineage):
    model_id = _register(registry, lineage)
    _full_approve(registry, model_id)
    promote_model(registry, model_id, "production")
    model = registry.get(model_id)
    assert model.state == LifecycleState.DEPLOYED
    assert model.deployed_to == "production"


def test_promote_without_approval_raises(registry, lineage):
    model_id = _register(registry, lineage)
    with pytest.raises(ValueError, match="APPROVED"):
        promote_model(registry, model_id, "production")


def test_retire_after_deploy(registry, lineage):
    model_id = _register(registry, lineage)
    _full_approve(registry, model_id)
    promote_model(registry, model_id, "production")
    retire_model(registry, model_id)
    assert registry.get(model_id).state == LifecycleState.RETIRED


def test_list_by_state(registry, lineage):
    id1 = _register(registry, lineage)
    id2 = register_model_candidate(
        registry, lineage, "model-b", "1.0", "team", "s3://b", "exp-2", "ds-v2"
    )
    _full_approve(registry, id2)
    approved = registry.list_models(state=LifecycleState.APPROVED)
    assert len(approved) == 1
    assert approved[0].model_id == id2
