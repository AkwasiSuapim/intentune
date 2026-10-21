"""The HTTP API (Prototype 1, phase B8): a thin FastAPI boundary over the application layer.

- settings.py: configuration from the process environment.
- container.py: the composition root. It builds the adapters once and fresh
  services, each with its own unit of work, for every request.
- app.py: create_app(), with startup and shutdown.
- errors.py: the error envelope and request IDs (spec §26).
- schemas.py: the request and response bodies (Pydantic), kept apart from
  domain and ORM models; views.py turns domain objects into them.
- routes/: one module per resource.

Run it with `python -m src.intentune.api` from backend/.
"""
