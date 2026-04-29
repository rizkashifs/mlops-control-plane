"""
MLflow-backed model registry.

Uses MLflow tracking to log each model as a run with params and tags.
Lifecycle state changes are recorded as MLflow tag updates.
An in-memory cache serves fast reads; MLflow provides the audit trail.
"""

from typing import Optional

import mlflow
from mlflow.tracking import MlflowClient

from .models import LifecycleState, ModelRecord


EXPERIMENT_NAME = "mlops-control-plane"

# Maps our states to MLflow Model Registry stages for observability
_MLFLOW_STAGE = {
    LifecycleState.CANDIDATE: "None",
    LifecycleState.VALIDATING: "None",
    LifecycleState.IN_REVIEW: "Staging",
    LifecycleState.APPROVED: "Staging",
    LifecycleState.DEPLOYED: "Production",
    LifecycleState.RETIRED: "Archived",
    LifecycleState.REJECTED: "Archived",
}


class MLflowModelRegistry:
    """
    Stores model lifecycle events in MLflow tracking.

    Each registered model becomes an MLflow run. State transitions update
    the run's 'lifecycle_state' tag so the full history is visible in the
    MLflow UI. Reads are served from an in-memory cache for speed.
    """

    def __init__(self, tracking_uri: str = "./mlruns"):
        mlflow.set_tracking_uri(tracking_uri)
        self._client = MlflowClient(tracking_uri=tracking_uri)
        self._run_ids: dict[str, str] = {}   # model_id → mlflow run_id
        self._cache: dict[str, ModelRecord] = {}

    def register(self, model: ModelRecord) -> str:
        mlflow.set_experiment(EXPERIMENT_NAME)
        with mlflow.start_run(run_name=f"{model.name}-{model.version}") as run:
            mlflow.log_params({
                "model_id": model.model_id,
                "name": model.name,
                "version": model.version,
                "owner": model.owner,
                "artifact_uri": model.artifact_uri,
            })
            mlflow.set_tag("lifecycle_state", model.state.value)

        self._run_ids[model.model_id] = run.info.run_id
        self._cache[model.model_id] = model
        return model.model_id

    def get(self, model_id: str) -> ModelRecord:
        if model_id not in self._cache:
            raise KeyError(f"Model '{model_id}' not found")
        return self._cache[model_id]

    def list_models(self, state: Optional[LifecycleState] = None) -> list[ModelRecord]:
        models = list(self._cache.values())
        if state:
            models = [m for m in models if m.state == state]
        return models

    def save(self, model: ModelRecord) -> None:
        self._cache[model.model_id] = model
        run_id = self._run_ids.get(model.model_id)
        if run_id:
            self._client.set_tag(run_id, "lifecycle_state", model.state.value)
            self._client.set_tag(run_id, "mlflow_stage", _MLFLOW_STAGE[model.state])
            if model.deployed_to:
                self._client.set_tag(run_id, "deployed_to", model.deployed_to)
