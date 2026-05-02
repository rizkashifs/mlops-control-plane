#!/usr/bin/env python3
"""
Full MLOps control plane lifecycle — runnable example.

Run from the repo root:
    python examples/lifecycle.py

No server required. Uses the Python API directly.
Demonstrates every lifecycle step from registration to retirement.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.audit import AuditLog
from src.core.config import load_config, required_approval_stages
from src.core.lineage import LineageStore
from src.core.models import ApprovalStage, ModelCard, ValidationEvidence
from src.core.registry import ModelRegistry
from src.pipelines.workflows import (
    approve_model,
    attach_model_card,
    attach_validation_evidence,
    promote_model,
    register_model_candidate,
    retire_model,
)

# ── Setup ──────────────────────────────────────────────────────────────────────

registry = ModelRegistry()
lineage  = LineageStore()
audit    = AuditLog()
config   = load_config()
required = required_approval_stages(config)

print("=" * 60)
print("  MLOps Control Plane — Full Lifecycle Demo")
print("=" * 60)

# ── Step 1: Register ───────────────────────────────────────────────────────────

print("\n[1/6] Training pipeline registers a model candidate")

model_id = register_model_candidate(
    registry=registry,
    lineage=lineage,
    name="fraud-detector",
    version="2.1.0",
    owner="risk-ml-team",
    artifact_uri="s3://models/fraud-detector/2.1.0/model.pkl",
    experiment_id="mlflow-exp-00142",
    dataset_version="transactions-2024-Q4-v3",
    tags={"model_type": "xgboost", "use_case": "fraud_detection"},
    audit_log=audit,
)

model = registry.get(model_id)
print(f"    model_id  : {model_id}")
print(f"    name      : {model.name} v{model.version}")
print(f"    state     : {model.state.value}")

# ── Step 2: Model card ─────────────────────────────────────────────────────────

print("\n[2/6] Author attaches governance documentation (model card)")

attach_model_card(
    registry, model_id,
    ModelCard(
        intended_use=(
            "Real-time fraud detection for card-not-present transactions. "
            "Scores 0–1; scores above 0.5 trigger a manual review queue."
        ),
        training_data_description=(
            "12 months of anonymised card transactions (Jan–Dec 2024), "
            "~4.2M rows, 0.8% fraud prevalence."
        ),
        known_limitations="Degrades on merchants first seen after Nov 2024 (cold-start).",
        out_of_scope_use="Not for credit scoring or identity verification.",
        ethical_considerations=(
            "Fairness evaluated across age and geography groups. "
            "False-positive rate disparity < 2% across evaluated segments."
        ),
        contact="risk-ml-team@example.com",
    ),
    actor="alice@example.com",
    audit_log=audit,
)

print("    model card attached.")

# ── Step 3: Validation evidence ────────────────────────────────────────────────

print("\n[3/6] Evaluation pipeline attaches metric evidence")

attach_validation_evidence(
    registry, model_id,
    [
        ValidationEvidence("accuracy", 0.9312, passed=True,
                           notes="Holdout set Oct–Dec 2024"),
        ValidationEvidence("f1",       0.8876, passed=True,
                           notes="Macro-averaged across classes"),
        ValidationEvidence("auc_roc",  0.9541, passed=True),
        ValidationEvidence("false_positive_rate", 0.034, passed=True,
                           notes="Threshold 0.5"),
    ],
    audit_log=audit,
)

model = registry.get(model_id)
print(f"    evidence items : {len(model.validation_evidence)}")
print(f"    state          : {model.state.value}")

# ── Step 4: Three-stage approval ───────────────────────────────────────────────

print("\n[4/6] Governance reviewers approve all required stages")

approvals = [
    (ApprovalStage.VALIDATION,          "alice@example.com",
     "All metrics exceed thresholds. Holdout evaluation confirmed."),
    (ApprovalStage.RISK_REVIEW,         "bob@example.com",
     "Fairness report reviewed. FP disparity within policy limits."),
    (ApprovalStage.PRODUCTION_APPROVAL, "carol@example.com",
     "Shadow deployment test passed. Capacity confirmed."),
]

for stage, reviewer, notes in approvals:
    approve_model(registry, model_id, stage, reviewer,
                  notes=notes, required_stages=required, audit_log=audit)
    current = registry.get(model_id).state.value
    print(f"    {stage.value:<26} approved by {reviewer}  →  state: {current}")

# ── Step 5: Promote ────────────────────────────────────────────────────────────

print("\n[5/6] Deploy bot promotes model to production")

promote_model(registry, model_id, "production",
              actor="deploy-bot@example.com", audit_log=audit)

model = registry.get(model_id)
print(f"    state       : {model.state.value}")
print(f"    deployed_to : {model.deployed_to}")

# ── Step 6: Retire ─────────────────────────────────────────────────────────────

print("\n[6/6] Next version ready — retire this model")

retire_model(registry, model_id,
             actor="deploy-bot@example.com", audit_log=audit)

print(f"    state : {registry.get(model_id).state.value}")

# ── Lineage ────────────────────────────────────────────────────────────────────

print("\n── Lineage ──────────────────────────────────────────────")
chain = lineage.get_lineage(model_id)
for node in chain["ancestry"]:
    print(f"    experiment  : {node['experiment_id']}")
    print(f"    dataset     : {node['dataset_version']}")

# ── Audit trail ────────────────────────────────────────────────────────────────

print("\n── Audit Trail ──────────────────────────────────────────")
for event in audit.get_events(model_id):
    transition = ""
    if event.from_state or event.to_state:
        transition = f"  ({event.from_state} → {event.to_state})"
    ts = event.timestamp.strftime("%H:%M:%S")
    print(f"    [{ts}] {event.event_type:<26} by {event.actor}{transition}")

print("\n" + "=" * 60)
print("  Done. All lifecycle steps completed successfully.")
print("=" * 60)
