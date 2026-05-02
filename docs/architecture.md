# Architecture

## Overview

The MLOps control plane manages the full lifecycle of ML models: from the moment a training pipeline produces a candidate artifact, through validation and multi-stage governance review, into production deployment, and finally retirement. It does not execute training or inference — it tracks state, metadata, lineage, and approval evidence.

## Component Map

```
Training Pipeline          Evaluation Pipeline        Deployment System
       |                          |                          |
       v                          v                          v
 register_model_candidate   attach_validation_evidence   promote_model
       |                          |                          |
       +------------- Control Plane API (FastAPI) -----------+
                                  |
          +-----------------------+-----------------------+
          v                       v                       v
    ModelRegistry           LineageStore              AuditLog
    (3 backends)           (ancestry chain)        (immutable trail)
          |
          v
     ModelRecord
       - LifecycleState
       - ValidationEvidence[]
       - ApprovalRecord[]
       - ModelCard
       - tags
```

## Lifecycle State Machine

```
CANDIDATE ──► IN_REVIEW ──► APPROVED ──► DEPLOYED ──► RETIRED
    │              │              │
    └──────────────┴──────────────┴──► REJECTED
```

State transitions are enforced in `src/pipelines/workflows.py`. The only way to advance state is through a workflow function — direct state mutation is not exposed via the API.

## Source Layout

```
src/
  core/
    models.py          Domain types: ModelRecord, LifecycleState, ModelCard, etc.
    registry.py        In-memory registry (default, no dependencies)
    registry_sql.py    SQLAlchemy/SQLite registry (persistent)
    registry_mlflow.py MLflow tracking registry (observability via MLflow UI)
    lineage.py         Experiment→model ancestry chain
    audit.py           Append-only event log for every state change
    config.py          Loads configs/config.yaml; exposes typed helpers
  pipelines/
    workflows.py       All lifecycle transition functions
  services/
    api.py             FastAPI application — routes, request/response models
configs/
  config.yaml          Registry backend, approval stages, metric thresholds
examples/
  01_register_model.json
  02_attach_validation_evidence.json
  03_attach_model_card.json
  04_approval_sequence.json
  05_promote_and_retire.json
  06_audit_response.json
tests/
  test_workflows.py    Core lifecycle tests (in-memory backend)
  test_backends.py     Same lifecycle run against all 3 backends
  test_enterprise.py   Audit log, model card, duplicate guard, inventory
```

## Registry Backends

| Backend  | Use case                             | Persistence | Observability      |
|----------|--------------------------------------|-------------|--------------------|
| `memory` | Local dev, testing                   | None        | None               |
| `sql`    | Single-node production, audit trails | SQLite file | Query the DB       |
| `mlflow` | Teams already running MLflow         | In-memory   | MLflow UI / search |

Select via `REGISTRY_BACKEND` env var or `registry.backend` in `config.yaml`.

## API Surface

| Method | Path                        | Purpose                                   |
|--------|-----------------------------|-------------------------------------------|
| GET    | /health                     | Liveness probe (Kubernetes)               |
| GET    | /inventory/summary          | Model counts by lifecycle state           |
| POST   | /models                     | Register a model candidate                |
| GET    | /models                     | List/search models                        |
| GET    | /models/{id}                | Full model record                         |
| GET    | /models/{id}/lineage        | Ancestry chain                            |
| POST   | /models/{id}/validate       | Attach metric evidence                    |
| POST   | /models/{id}/card           | Attach model card (governance docs)       |
| POST   | /models/{id}/approve        | Record a stage approval                   |
| POST   | /models/{id}/reject         | Record a stage rejection                  |
| POST   | /models/{id}/promote        | Promote to deployment environment         |
| POST   | /models/{id}/retire         | Retire a deployed model                   |
| GET    | /audit                      | Recent events (global)                    |
| GET    | /audit/{id}                 | Full event trail for one model            |

## Running Locally

```bash
# In-memory (default)
uvicorn src.services.api:app --reload

# SQL (SQLite)
REGISTRY_BACKEND=sql uvicorn src.services.api:app --reload

# MLflow
REGISTRY_BACKEND=mlflow uvicorn src.services.api:app --reload

# Interactive docs
open http://localhost:8000/docs
```
