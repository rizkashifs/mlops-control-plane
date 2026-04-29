# Architecture Decisions

## ADR-001: Control plane is separate from execution plane

The control plane tracks state, metadata, approvals, and governance. Training and inference workloads remain in execution systems.

## ADR-002: Promotion requires auditable state transitions

Models should move through lifecycle stages using explicit review events rather than ad hoc deployment scripts.
