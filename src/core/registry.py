from typing import Optional
from .models import ModelRecord, LifecycleState


class ModelRegistry:
    """In-memory store for model records."""

    def __init__(self):
        self._models: dict[str, ModelRecord] = {}

    def register(self, model: ModelRecord) -> str:
        self._models[model.model_id] = model
        return model.model_id

    def get(self, model_id: str) -> ModelRecord:
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found")
        return self._models[model_id]

    def list_models(self, state: Optional[LifecycleState] = None) -> list[ModelRecord]:
        models = list(self._models.values())
        if state:
            models = [m for m in models if m.state == state]
        return models

    def update_state(self, model_id: str, new_state: LifecycleState) -> None:
        self.get(model_id).state = new_state
