import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import httpx
import pytest
from app.main import app
from app.repositories.demo import DemoFireRepository
from app.repositories.provider import get_repository

ANCHOR = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def repository() -> DemoFireRepository:
    return DemoFireRepository(anchor=ANCHOR)


@pytest.fixture
def api(repository: DemoFireRepository) -> Iterator[Callable[[str], httpx.Response]]:
    app.dependency_overrides[get_repository] = lambda: repository

    def get(url: str) -> httpx.Response:
        async def request() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.get(url)

        return asyncio.run(request())

    yield get
    app.dependency_overrides.clear()
