"""
FastAPI control plane API.

Endpoints:
  GET  /health                      - liveness probe
  GET  /inventory/summary           - model counts by lifecycle state
  POST /models                      - register a model candidate
  GET  /models                      - list models (?state= ?name= ?owner= ?tag_key= ?tag_value=)
  GET  /models/{id}                 - get a model record
  GET  /models/{id}/lineage         - get full lineage chain
  POST /models/{id}/validate        - attach validation evidence
  POST /models/{id}/approve         - record a stage approval
  POST /models/{id}/reject          - record a stage rejection
  POST /models/{id}/promote         - promote to an environment
  POST /models/{id}/retire          - retire a deployed model
  POST /models/{id}/card            - attach a model card
  GET  /audit                       - recent audit events (global)
  GET  /audit/{id}                  - audit trail for one model
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from ..core.audit import AuditLog
from ..core.config import load_config, required_approval_stages
from ..core.lineage import LineageStore
from ..core.models import ApprovalStage, LifecycleState, ModelCard, ValidationEvidence
from ..core.registry import ModelRegistry
from ..core.registry_mlflow import MLflowModelRegistry
from ..core.registry_sql import SQLModelRegistry
from ..pipelines import workflows

app = FastAPI(title="MLOps Control Plane", version="0.2.0")

_config = load_config()
_required_stages = required_approval_stages(_config)


def _make_registry():
    backend = os.environ.get(
        "REGISTRY_BACKEND",
        _config.get("registry", {}).get("backend", "memory"),
    )
    if backend == "sql":
        url = _config.get("registry", {}).get("sql_url", "sqlite:///./control_plane.db")
        return SQLModelRegistry(url)
    if backend == "mlflow":
        uri = _config.get("registry", {}).get("mlflow_tracking_uri", "./mlruns")
        return MLflowModelRegistry(uri)
    return ModelRegistry()


registry = _make_registry()
lineage = LineageStore()
audit_log = AuditLog()


# --- Request / response models ---

class RegisterRequest(BaseModel):
    name: str
    version: str
    owner: str
    artifact_uri: str
    experiment_id: str
    dataset_version: str
    parent_model_id: Optional[str] = None
    tags: dict[str, str] = {}


class EvidenceItem(BaseModel):
    metric_name: str
    metric_value: float
    passed: bool
    notes: str = ""


class ApproveRequest(BaseModel):
    stage: ApprovalStage
    reviewer: str
    notes: str = ""


class RejectRequest(BaseModel):
    stage: ApprovalStage
    reviewer: str
    notes: str = ""


class PromoteRequest(BaseModel):
    environment: str
    actor: str = "system"


class RetireRequest(BaseModel):
    actor: str = "system"


class ModelCardRequest(BaseModel):
    intended_use: str
    training_data_description: str = ""
    known_limitations: str = ""
    out_of_scope_use: str = ""
    ethical_considerations: str = ""
    contact: str = ""
    actor: str = "system"


# --- Health & inventory ---

@app.get("/health")
def health():
    return {
        "status": "ok",
        "backend": os.environ.get("REGISTRY_BACKEND", _config.get("registry", {}).get("backend", "memory")),
    }


@app.get("/inventory/summary")
def inventory_summary():
    all_models = registry.list_models()
    by_state = {s.value: 0 for s in LifecycleState}
    for m in all_models:
        by_state[m.state.value] += 1
    return {"total": len(all_models), "by_state": by_state}


# --- Model CRUD & lifecycle ---

@app.post("/models", status_code=201)
def register_model(req: RegisterRequest):
    try:
        model_id = workflows.register_model_candidate(
            registry=registry,
            lineage=lineage,
            name=req.name,
            version=req.version,
            owner=req.owner,
            artifact_uri=req.artifact_uri,
            experiment_id=req.experiment_id,
            dataset_version=req.dataset_version,
            parent_model_id=req.parent_model_id,
            tags=req.tags,
            audit_log=audit_log,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"model_id": model_id}


@app.get("/models")
def list_models(
    state: Optional[str] = Query(default=None),
    name: Optional[str] = Query(default=None),
    owner: Optional[str] = Query(default=None),
    tag_key: Optional[str] = Query(default=None),
    tag_value: Optional[str] = Query(default=None),
):
    try:
        state_filter = LifecycleState(state) if state else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state '{state}'")

    models = registry.list_models(state=state_filter)

    if name:
        models = [m for m in models if name.lower() in m.name.lower()]
    if owner:
        models = [m for m in models if m.owner == owner]
    if tag_key and tag_value:
        models = [m for m in models if m.tags.get(tag_key) == tag_value]

    return [
        {
            "model_id": m.model_id,
            "name": m.name,
            "version": m.version,
            "owner": m.owner,
            "state": m.state,
            "registered_at": m.registered_at.isoformat(),
        }
        for m in models
    ]


@app.get("/models/{model_id}")
def get_model(model_id: str):
    try:
        m = registry.get(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "model_id": m.model_id,
        "name": m.name,
        "version": m.version,
        "owner": m.owner,
        "artifact_uri": m.artifact_uri,
        "state": m.state,
        "registered_at": m.registered_at.isoformat(),
        "deployed_to": m.deployed_to,
        "tags": m.tags,
        "model_card": (
            {
                "intended_use": m.model_card.intended_use,
                "training_data_description": m.model_card.training_data_description,
                "known_limitations": m.model_card.known_limitations,
                "out_of_scope_use": m.model_card.out_of_scope_use,
                "ethical_considerations": m.model_card.ethical_considerations,
                "contact": m.model_card.contact,
            }
            if m.model_card else None
        ),
        "validation_evidence": [
            {"metric_name": e.metric_name, "metric_value": e.metric_value, "passed": e.passed}
            for e in m.validation_evidence
        ],
        "approvals": [
            {"stage": a.stage, "approved": a.approved, "reviewer": a.reviewer, "notes": a.notes}
            for a in m.approvals
        ],
    }


@app.get("/models/{model_id}/lineage")
def get_lineage(model_id: str):
    try:
        registry.get(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return lineage.get_lineage(model_id)


@app.post("/models/{model_id}/validate")
def validate_model(model_id: str, evidence: list[EvidenceItem]):
    try:
        registry.get(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    workflows.attach_validation_evidence(
        registry,
        model_id,
        [ValidationEvidence(**e.model_dump()) for e in evidence],
        audit_log=audit_log,
    )
    return {"state": registry.get(model_id).state}


@app.post("/models/{model_id}/approve")
def approve_model(model_id: str, req: ApproveRequest):
    try:
        workflows.approve_model(
            registry, model_id, req.stage, req.reviewer, req.notes,
            audit_log=audit_log, required_stages=_required_stages,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"state": registry.get(model_id).state}


@app.post("/models/{model_id}/reject")
def reject_model(model_id: str, req: RejectRequest):
    try:
        workflows.reject_model(
            registry, model_id, req.reviewer, req.stage, req.notes,
            audit_log=audit_log,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"state": registry.get(model_id).state}


@app.post("/models/{model_id}/promote")
def promote_model(model_id: str, req: PromoteRequest):
    try:
        workflows.promote_model(
            registry, model_id, req.environment,
            actor=req.actor, audit_log=audit_log,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"state": registry.get(model_id).state, "deployed_to": req.environment}


@app.post("/models/{model_id}/retire")
def retire_model(model_id: str, req: RetireRequest):
    try:
        workflows.retire_model(registry, model_id, actor=req.actor, audit_log=audit_log)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"state": registry.get(model_id).state}


@app.post("/models/{model_id}/card")
def attach_model_card(model_id: str, req: ModelCardRequest):
    try:
        registry.get(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    card = ModelCard(
        intended_use=req.intended_use,
        training_data_description=req.training_data_description,
        known_limitations=req.known_limitations,
        out_of_scope_use=req.out_of_scope_use,
        ethical_considerations=req.ethical_considerations,
        contact=req.contact,
    )
    workflows.attach_model_card(registry, model_id, card, actor=req.actor, audit_log=audit_log)
    return {"status": "model card attached"}


# --- Audit ---

@app.get("/audit")
def get_audit_log(limit: int = Query(default=50, ge=1, le=500)):
    events = audit_log.get_all_events(limit=limit)
    return [_event_to_dict(e) for e in events]


@app.get("/audit/{model_id}")
def get_model_audit(model_id: str):
    try:
        registry.get(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [_event_to_dict(e) for e in audit_log.get_events(model_id)]


def _event_to_dict(e) -> dict:
    return {
        "event_id": e.event_id,
        "model_id": e.model_id,
        "event_type": e.event_type,
        "actor": e.actor,
        "from_state": e.from_state,
        "to_state": e.to_state,
        "details": e.details,
        "timestamp": e.timestamp.isoformat(),
    }
