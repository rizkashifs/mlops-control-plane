# mlops-control-plane

A platform control plane blueprint for managing machine learning models, experiments, approvals, metadata, and lineage across enterprise ML systems.

## Description

As ML adoption grows, organizations need a reliable way to know which models exist, who owns them, what data trained them, which experiments produced them, whether they were approved, where they are deployed, and when they should be retired.

This repository defines the architecture for an MLOps control plane. It does not execute training or inference workloads. Instead, it manages lifecycle state, metadata, governance, and promotion workflows for ML assets.

## Why This Matters

Without a control plane, teams often rely on scattered experiment logs, manual approvals, disconnected deployment scripts, and incomplete model inventories. This creates audit risk and slows production delivery.

An enterprise control plane gives platform teams a consistent surface for registry operations, approval workflows, lineage queries, and lifecycle reporting.

## High-Level Architecture

```text
Experiment Systems       Training Pipelines       Deployment Systems
       |                        |                         |
       v                        v                         v
  Experiment Events ---- Model Candidate Events ---- Deployment Events
       |                        |                         |
       +------------------------+-------------------------+
                                |
                                v
                         Control Plane API
                                |
        +-----------------------+-----------------------+
        v                       v                       v
  Model Registry          Metadata Store          Approval Workflow
        |                       |                       |
        v                       v                       v
  Lifecycle State          Lineage Graph          Audit Evidence
```

## Key Components

- `src/core`: Lifecycle models, registry contracts, lineage abstractions, and approval state definitions.
- `src/pipelines`: Placeholder workflows for model registration, validation evidence collection, review, promotion, and retirement.
- `src/services`: API and automation service boundaries for registry, metadata, and governance operations.
- `configs`: Control plane configuration placeholders.
- `docs`: Architecture notes and decision records.
- `examples`: Conceptual event payloads and lifecycle traces.

## Folder Structure

```text
mlops-control-plane/
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── core/
│   ├── pipelines/
│   └── services/
├── configs/
│   └── config.yaml
├── docs/
│   ├── architecture.md
│   └── decisions.md
└── examples/
```

## Example Workflows

### Model Registration

1. A training pipeline publishes a model candidate event.
2. The control plane records artifact references, metrics, dataset versions, and owner metadata.
3. Validation evidence is attached to the candidate.
4. The model becomes eligible for review.

### Approval and Promotion

1. A reviewer inspects metrics, lineage, model card data, and risk evidence.
2. Approval state changes are recorded as immutable events.
3. A production promotion request is sent to the deployment system.
4. The control plane tracks the deployed version and environment.

## Design Decisions and Tradeoffs

- Control plane separation: improves governance and consistency, but requires integration with external execution systems.
- Event-driven lifecycle: creates auditability, but teams need reliable event contracts.
- Central metadata model: enables enterprise reporting, but must remain flexible enough for diverse model types.
- Explicit approval state: reduces informal deployment risk, but can slow urgent releases without exception handling.

## Future Roadmap

- Define lifecycle event schemas.
- Add model registry API contract examples.
- Add approval workflow templates for risk, security, and business review.
- Add lineage graph model examples.
- Add dashboards for inventory, deployment status, and retirement candidates.
