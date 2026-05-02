"""
Immutable audit log for all model lifecycle events.

Every state change, approval, validation, and promotion is recorded here.
This log is the primary evidence artifact for compliance and governance audits.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


@dataclass
class AuditEvent:
    model_id: str
    event_type: str   # registered | evidence_attached | stage_approved | stage_rejected
                      # promoted | retired | model_card_attached
    actor: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    details: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLog:
    """Append-only in-memory event log. Every write is permanent within the session."""

    def __init__(self):
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    def get_events(self, model_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.model_id == model_id]

    def get_all_events(self, limit: int = 200) -> list[AuditEvent]:
        return list(reversed(self._events[-limit:]))
