"""Business logic: services orchestrate repositories inside transactions.

Rules: no FastAPI imports, no SQLAlchemy imports (sessions arrive via DI),
raise AppError (never HTTPException). Canonical minimal service: readiness.py.
"""
