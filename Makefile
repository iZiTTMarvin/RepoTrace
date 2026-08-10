.PHONY: backend frontend test benchmark dev

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest -q

benchmark:
	cd backend && python -m scripts.run_benchmark

