"""GET /health: the process is up and serving."""

from fastapi import APIRouter

from src.intentune.api.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut()
