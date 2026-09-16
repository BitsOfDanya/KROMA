from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.models.burn_scar import BurnScar
from app.repositories.base import FireDataRepository
from app.repositories.provider import get_repository
from app.schemas.burn_scars import BurnScarList
from app.services.burn_scars import BurnScarService

router = APIRouter(prefix="/burn-scars", tags=["burn-scars"])
Repository = Annotated[FireDataRepository, Depends(get_repository)]


@router.get("", response_model=BurnScarList)
def list_burn_scars(
    repository: Repository,
    region: Annotated[str | None, Query(max_length=64)] = None,
    min_area_ha: Annotated[float | None, Query(ge=0)] = None,
) -> BurnScarList:
    return BurnScarService(repository).list(region, min_area_ha)


@router.get("/{burn_scar_id}", response_model=BurnScar)
def get_burn_scar(burn_scar_id: str, repository: Repository) -> BurnScar:
    return BurnScarService(repository).get(burn_scar_id)
