# mlops-control-plane

A working control plane for managing ML model lifecycle, governance approvals, lineage, and audit evidence across enterprise ML systems.

---

## Control Plane vs Data Plane

This is a **control plane**, not a data plane:

| Aspect | Control Plane (this project) | Data Plane |
|--------|-----|----------|
| **Purpose** | Manages state, approvals, and audit trail | Executes predictions or inference |
| **Role** | "Is this model approved for production?" | "What prediction does this model make?" |
| **Data** | Model metadata, governance records, event log | Input features, model scores, predictions |
| **Latency** | Humans approve (hours/days) | Milliseconds (real-time) |
| **Storage** | Registry (who, when, why) | Feature store / prediction cache |
| **Example** | Register candidate → attach evidence → 3-stage approval → deploy | Load model → run inference → return score |

This control plane **coordinates** between training pipelines (which produce candidates), governance teams (who approve), and deployment systems (which execute). It does not train models or serve predictions itself.

---

## What it does

Tracks every model from the moment a training pipeline produces a candidate artifact through validation, multi-stage governance review, production deployment, and retirement. It does **not** train models or serve predictions — it manages state, metadata, approvals, and the audit trail.

**Lifecycle flow:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Model Lifecycle State Machine                 │
└─────────────────────────────────────────────────────────────────┘

    register_model_candidate()
           │
           ▼
       CANDIDATE
           │
           ├─ attach_validation_evidence()
           │  (all metrics pass)
           │
           ▼
       IN_REVIEW
           │
           ├─ approve_model() × 3 stages
           │  (validation → risk_review → production_approval)
           │
           ▼
       APPROVED
           │
           ├─ promote_model()
           │
           ▼
       DEPLOYED
           │
           ├─ retire_model()
           │
           ▼
       RETIRED

    ⚠️  REJECTED branch (if any approval fails):
           CANDIDATE ──→ IN_REVIEW ──→ REJECTED
```

**Example: A real governance workflow**

```
Training Pipeline     →   register_model_candidate(fraud-detector v2.1.0)   →   CANDIDATE
Model Author          →   attach_model_card(intended_use, limitations, ...)   →   (still CANDIDATE)
Evaluation Pipeline   →   attach_validation_evidence(accuracy, f1, auc, ...)  →   IN_REVIEW
Data Governance       →   approve_model(VALIDATION_STAGE)                      →   (still IN_REVIEW)
Risk Compliance       →   approve_model(RISK_REVIEW_STAGE)                     →   (still IN_REVIEW)
DevOps Lead           →   approve_model(PRODUCTION_APPROVAL_STAGE)             →   APPROVED
Deploy Bot            →   promote_model(environment="production")              →   DEPLOYED
6 months later...
Platform Team         →   retire_model()                                       →   RETIRED
```

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the API server (in-memory backend, no setup needed)
python main.py

# 3. Open interactive API docs
open http://localhost:8000/docs

# 4. Run the full lifecycle example (no server needed)
python examples/lifecycle.py
```

Or with Make:

```bash
make install
make run        # in-memory
make run-sql    # SQLite (persistent)
make run-mlflow # MLflow tracking
make example    # run lifecycle demo
make test       # run all tests
```

---

## Docker

Run in a container with any backend:

**In-memory backend (no persistence):**
```bash
docker build -t mlops-control-plane .
docker run -p 8000:8000 -e REGISTRY_BACKEND=memory mlops-control-plane
```

**All backends at once (docker-compose):**
```bash
docker-compose up

# Now you have:
# - app-memory    at http://localhost:8000/docs (in-memory, no persistence)
# - app-sql       at http://localhost:8001/docs (SQLite, data/ volume)
# - mlflow-server at http://localhost:5000 (MLflow UI)
# - app-mlflow    at http://localhost:8002/docs (MLflow backend)
```

**Run a specific backend:**
```bash
docker-compose up app-sql      # SQLite only
docker-compose up app-mlflow   # MLflow + MLflow server
```

**Tear down:**
```bash
docker-compose down
docker volume prune  # Clean up volumes if needed
```

---

## Full lifecycle example

```bash
python examples/lifecycle.py
```

Output:

```
============================================================
  MLOps Control Plane — Full Lifecycle Demo
============================================================

[1/6] Training pipeline registers a model candidate
    model_id  : 608bf12d-...
    name      : fraud-detector v2.1.0
    state     : candidate

[2/6] Author attaches governance documentation (model card)
    model card attached.

[3/6] Evaluation pipeline attaches metric evidence
    evidence items : 4
    state          : in_review

[4/6] Governance reviewers approve all required stages
    validation                 approved by alice@example.com  →  state: in_review
    risk_review                approved by bob@example.com   →  state: in_review
    production_approval        approved by carol@example.com →  state: approved

[5/6] Deploy bot promotes model to production
    state       : deployed
    deployed_to : production

[6/6] Next version ready — retire this model
    state : retired

── Audit Trail ──────────────────────────────────────────
    [09:00:01] registered              by risk-ml-team         (None → candidate)
    [09:00:02] model_card_attached     by alice@example.com
    [09:00:03] evidence_attached       by system               (candidate → in_review)
    [09:00:04] stage_approved          by alice@example.com    (in_review → in_review)
    [09:00:05] stage_approved          by bob@example.com      (in_review → in_review)
    [09:00:06] stage_approved          by carol@example.com    (in_review → approved)
    [09:00:07] promoted                by deploy-bot           (approved → deployed)
    [09:00:08] retired                 by deploy-bot           (deployed → retired)
```

The example uses the Python API directly — no server needed. See [`examples/lifecycle.py`](examples/lifecycle.py).

---

## API reference

Full interactive docs at `http://localhost:8000/docs` once the server is running.
The machine-readable spec is at [`openapi.json`](openapi.json).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness probe (Kubernetes) |
| `GET` | `/inventory/summary` | Model counts by lifecycle state |
| `POST` | `/models` | Register a model candidate |
| `GET` | `/models` | List / search models (`?state=` `?name=` `?owner=` `?tag_key=` `?tag_value=`) |
| `GET` | `/models/{id}` | Full model record |
| `GET` | `/models/{id}/lineage` | Experiment → model ancestry chain |
| `POST` | `/models/{id}/validate` | Attach metric evidence |
| `POST` | `/models/{id}/card` | Attach model card (governance docs) |
| `POST` | `/models/{id}/approve` | Record a stage approval |
| `POST` | `/models/{id}/reject` | Record a stage rejection |
| `POST` | `/models/{id}/promote` | Promote to a deployment environment |
| `POST` | `/models/{id}/retire` | Retire a deployed model |
| `GET` | `/audit` | Recent events across all models |
| `GET` | `/audit/{id}` | Full audit trail for one model |

Example requests are in [`examples/`](examples/).

---

## Choosing a backend

Set `REGISTRY_BACKEND` or edit `configs/config.yaml`:

| Backend | When to use | Persistence |
|---------|-------------|-------------|
| `memory` | Local dev and tests | None (resets on restart) |
| `sql` | Single-node production | SQLite file (`control_plane.db`) |
| `mlflow` | Teams already running MLflow | In-memory + MLflow run tags |

```bash
REGISTRY_BACKEND=sql python main.py
```

---

## Configuration

Edit [`configs/config.yaml`](configs/config.yaml):

```yaml
registry:
  backend: memory          # memory | sql | mlflow

approval:
  required_stages:         # remove stages for lighter-weight governance paths
    - validation
    - risk_review
    - production_approval

metrics:
  thresholds:              # reference values — callers decide pass/fail today
    accuracy: 0.85
    f1: 0.80
```

---

## Project structure

```
mlops-control-plane/
├── main.py                     Entry point — starts the API server
├── Makefile                    Common tasks: run, test, example, openapi
├── Dockerfile                  Container image definition
├── docker-compose.yml          Multi-backend service setup
├── .dockerignore                Files excluded from image
├── requirements.txt
├── openapi.json                Machine-readable API spec
├── configs/
│   └── config.yaml             Backend, approval stages, metric thresholds
├── src/
│   ├── core/
│   │   ├── models.py           Domain types (ModelRecord, LifecycleState, ModelCard …)
│   │   ├── registry.py         In-memory registry
│   │   ├── registry_sql.py     SQLAlchemy / SQLite registry
│   │   ├── registry_mlflow.py  MLflow tracking registry
│   │   ├── lineage.py          Experiment → model ancestry store
│   │   ├── audit.py            Append-only event log
│   │   └── config.py           Config loader
│   ├── pipelines/
│   │   └── workflows.py        Lifecycle transition functions
│   └── services/
│       └── api.py              FastAPI application
├── examples/
│   ├── lifecycle.py            Runnable end-to-end lifecycle demo
│   ├── 01_register_model.json
│   ├── 02_attach_validation_evidence.json
│   ├── 03_attach_model_card.json
│   ├── 04_approval_sequence.json
│   ├── 05_promote_and_retire.json
│   └── 06_audit_response.json
├── tests/
│   ├── test_workflows.py       Core lifecycle tests
│   ├── test_backends.py        Same tests across all 3 backends
│   └── test_enterprise.py      Audit, model card, duplicate guard, config
└── docs/
    ├── architecture.md         Component map, state machine, API surface
    └── decisions.md            Architecture Decision Records (ADRs)
```

---

## Running tests

```bash
make test
# or
python -m pytest tests/ -v
```

64 tests — core lifecycle, all three backends, enterprise features.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the component map, state machine diagram, and backend comparison.

See [`docs/decisions.md`](docs/decisions.md) for the Architecture Decision Records covering tradeoffs in audit durability, model card enforcement, swappable backends, and config-driven governance.
