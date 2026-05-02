.PHONY: install run run-sql run-mlflow test example openapi

install:
	pip install -r requirements.txt

run:
	uvicorn src.services.api:app --reload --host 0.0.0.0 --port 8000

run-sql:
	REGISTRY_BACKEND=sql uvicorn src.services.api:app --reload --host 0.0.0.0 --port 8000

run-mlflow:
	REGISTRY_BACKEND=mlflow uvicorn src.services.api:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest tests/ -v

example:
	python examples/lifecycle.py

openapi:
	python -c "import json; from src.services.api import app; open('openapi.json','w').write(json.dumps(app.openapi(), indent=2))"
	@echo "Written to openapi.json"
