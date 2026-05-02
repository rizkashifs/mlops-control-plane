"""
SQL-backed model registry using SQLAlchemy + SQLite.

All model state (including evidence and approvals) is persisted to the DB.
Lists are stored as JSON columns.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, Column, String, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, Session

import dataclasses

from .models import (
    ApprovalRecord,
    ApprovalStage,
    LifecycleState,
    ModelCard,
    ModelRecord,
    ValidationEvidence,
)


class _Base(DeclarativeBase):
    pass


class _ModelRow(_Base):
    __tablename__ = "models"

    model_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    owner = Column(String, nullable=False)
    artifact_uri = Column(String, nullable=False)
    state = Column(String, nullable=False)
    registered_at = Column(DateTime, nullable=False)
    deployed_to = Column(String, nullable=True)
    tags = Column(JSON, default={})
    validation_evidence = Column(JSON, default=[])
    approvals = Column(JSON, default=[])
    model_card = Column(JSON, nullable=True)


class SQLModelRegistry:
    """Persists model records in a SQLite database."""

    def __init__(self, db_url: str = "sqlite:///./control_plane.db"):
        self._engine = create_engine(db_url)
        _Base.metadata.create_all(self._engine)

    def register(self, model: ModelRecord) -> str:
        with Session(self._engine) as session:
            session.add(_ModelRow(
                model_id=model.model_id,
                name=model.name,
                version=model.version,
                owner=model.owner,
                artifact_uri=model.artifact_uri,
                state=model.state.value,
                registered_at=model.registered_at,
                deployed_to=model.deployed_to,
                tags=model.tags,
                validation_evidence=[],
                approvals=[],
            ))
            session.commit()
        return model.model_id

    def get(self, model_id: str) -> ModelRecord:
        with Session(self._engine) as session:
            row = session.get(_ModelRow, model_id)
            if row is None:
                raise KeyError(f"Model '{model_id}' not found")
            return _row_to_record(row)

    def list_models(self, state: Optional[LifecycleState] = None) -> list[ModelRecord]:
        with Session(self._engine) as session:
            query = session.query(_ModelRow)
            if state:
                query = query.filter(_ModelRow.state == state.value)
            return [_row_to_record(r) for r in query.all()]

    def save(self, model: ModelRecord) -> None:
        with Session(self._engine) as session:
            row = session.get(_ModelRow, model.model_id)
            if row is None:
                raise KeyError(f"Model '{model.model_id}' not found")
            row.state = model.state.value
            row.deployed_to = model.deployed_to
            row.validation_evidence = [_evidence_to_dict(e) for e in model.validation_evidence]
            row.approvals = [_approval_to_dict(a) for a in model.approvals]
            row.model_card = dataclasses.asdict(model.model_card) if model.model_card else None
            session.commit()


# --- serialization helpers ---

def _evidence_to_dict(e: ValidationEvidence) -> dict:
    return {"metric_name": e.metric_name, "metric_value": e.metric_value,
            "passed": e.passed, "notes": e.notes}


def _approval_to_dict(a: ApprovalRecord) -> dict:
    return {"stage": a.stage.value, "approved": a.approved, "reviewer": a.reviewer,
            "timestamp": a.timestamp.isoformat(), "notes": a.notes}


def _row_to_record(row: _ModelRow) -> ModelRecord:
    model = ModelRecord(
        model_id=row.model_id,
        name=row.name,
        version=row.version,
        owner=row.owner,
        artifact_uri=row.artifact_uri,
        state=LifecycleState(row.state),
        registered_at=row.registered_at,
        deployed_to=row.deployed_to,
        tags=row.tags or {},
    )
    model.model_card = ModelCard(**row.model_card) if row.model_card else None
    model.validation_evidence = [
        ValidationEvidence(**d) for d in (row.validation_evidence or [])
    ]
    model.approvals = [
        ApprovalRecord(
            stage=ApprovalStage(d["stage"]),
            approved=d["approved"],
            reviewer=d["reviewer"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            notes=d.get("notes", ""),
        )
        for d in (row.approvals or [])
    ]
    return model
