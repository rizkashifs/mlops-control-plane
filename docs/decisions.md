# Architecture Decisions

## ADR-001: Control plane is separate from execution plane

The control plane tracks state, metadata, approvals, and governance. Training and inference workloads remain in execution systems. This separation means any training framework (Spark, Ray, SageMaker) can integrate by emitting a single registration event.

**Tradeoff:** teams need reliable event contracts between execution systems and the control plane. A broken event pipeline can leave models stuck in CANDIDATE state.

## ADR-002: Promotion requires auditable state transitions

Models advance through lifecycle stages only via explicit workflow functions. There is no "force promote" endpoint. Each transition is recorded in the AuditLog with actor, timestamp, and context.

**Tradeoff:** this slows emergency releases. Mitigation: add an expedited `exception_promote` workflow with mandatory justification that bypasses normal stages but still creates a full audit record.

## ADR-003: Audit log is append-only and in-memory

The `AuditLog` class is an append-only list — events cannot be deleted or modified. The current implementation is in-memory for simplicity. For production, extend it with a SQL backend (a separate `audit_events` table) so the log survives restarts and can be queried for compliance reports.

**Tradeoff:** the in-memory log is lost on restart. Teams that need durable audit trails before the SQL audit backend is built should use the MLflow registry backend, which writes all state changes as immutable run tags.

## ADR-004: Model card is required before production approval

The `ModelCard` dataclass captures intended use, known limitations, training data description, and ethical considerations. It must be attached before a governance reviewer can meaningfully approve `production_approval`. The API does not enforce this as a hard block today — reviewers are expected to check.

**Tradeoff:** soft enforcement is easier to adopt but less safe. Teams with stricter governance can add a check in `approve_model` that raises if `model.model_card is None` and `stage == PRODUCTION_APPROVAL`.

## ADR-005: Three swappable registry backends behind one interface

`ModelRegistry` (memory), `SQLModelRegistry` (SQLAlchemy/SQLite), and `MLflowModelRegistry` (MLflow tracking) all expose the same four methods: `register`, `get`, `list_models`, `save`. Switching is a one-line env var change (`REGISTRY_BACKEND`).

**Tradeoff:** the MLflow backend currently stores evidence and approvals only in the in-memory cache — MLflow run tags hold state metadata but not the full list of approval records. Teams using the MLflow backend in production should add a companion SQL store for full record persistence.

## ADR-006: Config drives required approval stages

Required approval stages are read from `configs/config.yaml` at startup. This means platform teams can customize governance workflows (e.g., a lighter-weight process for internal tools vs. customer-facing models) without code changes.

**Tradeoff:** different model types may need different approval paths. A future extension would allow per-model-name or per-tag overrides of required stages.
