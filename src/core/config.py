"""
Loads configs/config.yaml and exposes typed helpers used across the codebase.
"""

from pathlib import Path
from typing import Optional

import yaml

from .models import ApprovalStage

_DEFAULT_REQUIRED_STAGES = {
    ApprovalStage.VALIDATION,
    ApprovalStage.RISK_REVIEW,
    ApprovalStage.PRODUCTION_APPROVAL,
}


def load_config(path: str = "configs/config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def required_approval_stages(config: Optional[dict] = None) -> set[ApprovalStage]:
    if not config:
        return _DEFAULT_REQUIRED_STAGES
    stage_names = config.get("approval", {}).get("required_stages", [])
    if not stage_names:
        return _DEFAULT_REQUIRED_STAGES
    return {ApprovalStage(s) for s in stage_names}
