from functools import lru_cache

from app.core.config import get_settings
from app.repositories.base import FireDataRepository
from app.repositories.demo import DemoFireRepository


@lru_cache
def get_repository() -> FireDataRepository:
    settings = get_settings()
    return DemoFireRepository(anchor=settings.demo_anchor)
