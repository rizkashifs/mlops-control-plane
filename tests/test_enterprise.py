"""
Tests for enterprise features:
  - Audit log (event capture, actor, state transitions)
  - ModelCard (attach, persist, retrieve)
  - Duplicate registration guard
  - Config-driven approval stages
  - Inventory summary (via registry queries)
"""

import pytest

from src.core.audit import AuditLog
from src.core.config import load_config, required_approval_stages
from src.core.lineage import LineageStore
from src.core.models import ApprovalStage, LifecycleState, ModelCard, ValidationEvidence
from src.core.registry import ModelRegistry
from src.pipelines.workflows import (
    approve_model,
    attach_model_card,
    attach_validation_evidence,
    promote_model,
    register_model_candidate,
    reject_model,
    retire_model,
)


@pytest.fixture
def ctx():
    return ModelRegistry(), LineageStore(), AuditLog()


def _register(registry, lineage, audit_log=None, name="churn-model", version="1.0"):
    return register_model_candidate(
        registry=registry,
        lineage=lineage,
        name=name,
        version=version,
        owner="ml-team",
        artifact_uri="s3://models/churn/1.0",
        experiment_id="exp-01",
        dataset_version="ds-v1",
        audit_log=audit_log,
    )


def _full_approve(registry, model_id, audit_log=None):
    for stage in ApprovalStage:
        approve_model(registry, model_id, stage, reviewer="alice", audit_log=audit_log)


# --- Audit log ---

def test_registration_creates_audit_event(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage, audit_log)
    events = audit_log.get_events(model_id)
    assert len(events) == 1
    assert events[0].event_type == "registered"
    assert events[0].actor == "ml-team"
    assert events[0].to_state == "candidate"


def test_validation_creates_audit_event(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage, audit_log)
    attach_validation_evidence(registry, model_id, [
        ValidationEvidence("accuracy", 0.92, passed=True),
    ], audit_log=audit_log)
    events = audit_log.get_events(model_id)
    ev_types = [e.event_type for e in events]
    assert "evidence_attached" in ev_types


def test_approval_creates_audit_event(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage, audit_log)
    approve_model(registry, model_id, ApprovalStage.VALIDATION, "alice", audit_log=audit_log)
    events = audit_log.get_events(model_id)
    approval_events = [e for e in events if e.event_type == "stage_approved"]
    assert len(approval_events) == 1
    assert approval_events[0].actor == "alice"
    assert approval_events[0].details["stage"] == "validation"


def test_rejection_creates_audit_event(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage, audit_log)
    reject_model(registry, model_id, "bob", ApprovalStage.RISK_REVIEW, "too risky", audit_log=audit_log)
    events = audit_log.get_events(model_id)
    assert any(e.event_type == "stage_rejected" for e in events)


def test_full_lifecycle_audit_trail(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage, audit_log)
    attach_validation_evidence(registry, model_id, [
        ValidationEvidence("f1", 0.9, passed=True),
    ], audit_log=audit_log)
    _full_approve(registry, model_id, audit_log)
    promote_model(registry, model_id, "production", actor="deploy-bot", audit_log=audit_log)
    retire_model(registry, model_id, actor="deploy-bot", audit_log=audit_log)

    events = audit_log.get_events(model_id)
    event_types = [e.event_type for e in events]
    assert "registered" in event_types
    assert "evidence_attached" in event_types
    assert "stage_approved" in event_types
    assert "promoted" in event_types
    assert "retired" in event_types


def test_audit_promotion_records_environment(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage, audit_log)
    _full_approve(registry, model_id, audit_log)
    promote_model(registry, model_id, "production", actor="deploy-bot", audit_log=audit_log)
    promoted = next(e for e in audit_log.get_events(model_id) if e.event_type == "promoted")
    assert promoted.details["environment"] == "production"
    assert promoted.actor == "deploy-bot"


def test_get_all_events_returns_most_recent_first(ctx):
    registry, lineage, audit_log = ctx
    id1 = _register(registry, lineage, audit_log, name="m1")
    id2 = _register(registry, lineage, audit_log, name="m2")
    all_events = audit_log.get_all_events()
    assert all_events[0].model_id == id2  # most recent first
    assert all_events[1].model_id == id1


# --- ModelCard ---

def test_attach_model_card(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage)
    card = ModelCard(
        intended_use="Fraud detection for CNP transactions",
        known_limitations="Cold-start on new merchants",
        contact="ml-team@example.com",
    )
    attach_model_card(registry, model_id, card, actor="alice", audit_log=audit_log)
    retrieved = registry.get(model_id).model_card
    assert retrieved is not None
    assert retrieved.intended_use == "Fraud detection for CNP transactions"
    assert retrieved.contact == "ml-team@example.com"


def test_model_card_audit_event(ctx):
    registry, lineage, audit_log = ctx
    model_id = _register(registry, lineage, audit_log)
    attach_model_card(
        registry, model_id,
        ModelCard(intended_use="Test use"),
        actor="alice", audit_log=audit_log,
    )
    events = audit_log.get_events(model_id)
    assert any(e.event_type == "model_card_attached" for e in events)


def test_model_card_persists_in_sql(tmp_path):
    from src.core.registry_sql import SQLModelRegistry
    registry = SQLModelRegistry(f"sqlite:///{tmp_path}/test.db")
    lineage = LineageStore()
    model_id = register_model_candidate(
        registry, lineage, "m", "1", "owner", "s3://x", "exp", "ds"
    )
    attach_model_card(
        registry, model_id,
        ModelCard(intended_use="SQL persistence test", contact="test@x.com"),
    )
    retrieved = registry.get(model_id).model_card
    assert retrieved.intended_use == "SQL persistence test"
    assert retrieved.contact == "test@x.com"


# --- Duplicate registration guard ---

def test_duplicate_registration_raises(ctx):
    registry, lineage, _ = ctx
    _register(registry, lineage, name="fraud-model", version="1.0")
    with pytest.raises(ValueError, match="already registered"):
        _register(registry, lineage, name="fraud-model", version="1.0")


def test_different_version_allowed(ctx):
    registry, lineage, _ = ctx
    _register(registry, lineage, name="fraud-model", version="1.0")
    id2 = _register(registry, lineage, name="fraud-model", version="2.0")
    assert id2 is not None


# --- Config-driven approval stages ---

def test_config_loads_required_stages(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "approval:\n  required_stages:\n    - validation\n    - risk_review\n"
    )
    config = load_config(str(config_file))
    stages = required_approval_stages(config)
    assert ApprovalStage.VALIDATION in stages
    assert ApprovalStage.RISK_REVIEW in stages
    assert ApprovalStage.PRODUCTION_APPROVAL not in stages


def test_custom_required_stages_approve_with_fewer_stages(ctx):
    registry, lineage, _ = ctx
    model_id = _register(registry, lineage)
    # Only require validation (skip risk_review and production_approval)
    approve_model(
        registry, model_id, ApprovalStage.VALIDATION, "alice",
        required_stages={ApprovalStage.VALIDATION},
    )
    assert registry.get(model_id).state == LifecycleState.APPROVED


# --- Inventory ---

def test_inventory_counts_by_state(ctx):
    registry, lineage, _ = ctx
    id1 = _register(registry, lineage, name="m1")
    id2 = _register(registry, lineage, name="m2")
    id3 = _register(registry, lineage, name="m3")
    _full_approve(registry, id2)
    _full_approve(registry, id3)
    promote_model(registry, id3, "production")

    candidates = registry.list_models(state=LifecycleState.CANDIDATE)
    approved = registry.list_models(state=LifecycleState.APPROVED)
    deployed = registry.list_models(state=LifecycleState.DEPLOYED)

    assert len(candidates) == 1
    assert len(approved) == 1
    assert len(deployed) == 1
