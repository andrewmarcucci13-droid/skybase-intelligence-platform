web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: celery -A app.tasks.orchestrator:celery_app worker --loglevel=info --concurrency=2
