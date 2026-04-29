from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid


class LifecycleState(str, Enum):
    CANDIDATE = "candidate"
    VALIDATING = "validating"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    RETIRED = "retired"
    REJECTED = "rejected"


class ApprovalStage(str, Enum):
    VALIDATION = "validation"
    RISK_REVIEW = "risk_review"
    PRODUCTION_APPROVAL = "production_approval"


@dataclass
class ValidationEvidence:
    metric_name: str
    metric_value: float
    passed: bool
    notes: str = ""


@dataclass
class ApprovalRecord:
    stage: ApprovalStage
    approved: bool
    reviewer: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""


@dataclass
class ModelRecord:
    name: str
    version: str
    owner: str
    artifact_uri: str
    model_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: LifecycleState = LifecycleState.CANDIDATE
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    validation_evidence: list[ValidationEvidence] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    deployed_to: Optional[str] = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class LineageRecord:
    model_id: str
    experiment_id: str
    dataset_version: str
    parent_model_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
