"""
FastAPI control plane API.

Endpoints:
  POST /models                     - register a model candidate
  GET  /models                     - list all models (optional ?state= filter)
  GET  /models/{id}                - get a model record
  GET  /models/{id}/lineage        - get lineage chain
  POST /models/{id}/validate       - attach validation evidence
  POST /models/{id}/approve        - record an approval
  POST /models/{id}/reject         - record a rejection
  POST /models/{id}/promote        - promote to an environment
  POST /models/{id}/retire         - retire a deployed model
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from ..core.models import ApprovalStage, LifecycleState, ValidationEvidence
from ..core.registry import ModelRegistry
from ..core.lineage import LineageStore
from ..pipelines import workflows

app = FastAPI(title="MLOps Control Plane")

registry = ModelRegistry()
lineage = LineageStore()


# --- Request bodies ---

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


# --- Routes ---

@app.post("/models", status_code=201)
def register_model(req: RegisterRequest):
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
    )
    return {"model_id": model_id}


@app.get("/models")
def list_models(state: Optional[str] = Query(default=None)):
    state_filter = LifecycleState(state) if state else None
    models = registry.list_models(state=state_filter)
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
    )
    return {"state": registry.get(model_id).state}


@app.post("/models/{model_id}/approve")
def approve_model(model_id: str, req: ApproveRequest):
    try:
        workflows.approve_model(registry, model_id, req.stage, req.reviewer, req.notes)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"state": registry.get(model_id).state}


@app.post("/models/{model_id}/reject")
def reject_model(model_id: str, req: RejectRequest):
    try:
        workflows.reject_model(registry, model_id, req.reviewer, req.stage, req.notes)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"state": registry.get(model_id).state}


@app.post("/models/{model_id}/promote")
def promote_model(model_id: str, req: PromoteRequest):
    try:
        workflows.promote_model(registry, model_id, req.environment)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"state": registry.get(model_id).state, "deployed_to": req.environment}


@app.post("/models/{model_id}/retire")
def retire_model(model_id: str):
    try:
        workflows.retire_model(registry, model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"state": registry.get(model_id).state}
