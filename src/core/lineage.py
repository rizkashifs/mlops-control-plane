from typing import Optional
from .models import LineageRecord


class LineageStore:
    """Tracks the lineage chain: experiment → model → parent model."""

    def __init__(self):
        self._records: dict[str, LineageRecord] = {}

    def record(
        self,
        model_id: str,
        experiment_id: str,
        dataset_version: str,
        parent_model_id: Optional[str] = None,
    ) -> None:
        self._records[model_id] = LineageRecord(
            model_id=model_id,
            experiment_id=experiment_id,
            dataset_version=dataset_version,
            parent_model_id=parent_model_id,
        )

    def get_lineage(self, model_id: str) -> dict:
        """Return the full ancestry chain for a model."""
        chain = []
        current_id = model_id
        seen = set()

        while current_id and current_id not in seen:
            seen.add(current_id)
            rec = self._records.get(current_id)
            if rec is None:
                break
            chain.append({
                "model_id": rec.model_id,
                "experiment_id": rec.experiment_id,
                "dataset_version": rec.dataset_version,
                "parent_model_id": rec.parent_model_id,
                "created_at": rec.created_at.isoformat(),
            })
            current_id = rec.parent_model_id

        return {"model_id": model_id, "ancestry": chain}
