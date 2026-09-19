from fastapi import APIRouter

from app.services.ml_service import get_ml_service

router = APIRouter()


@router.get("/health")
def health() -> dict:
    state = get_ml_service().status()
    return {
        "status": "ok",
        **{k: state[k] for k in ("version", "af", "bs", "device", "missing_artifacts")},
    }


@router.get("/models")
def models() -> dict:
    return get_ml_service().status()
