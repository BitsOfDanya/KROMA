import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.v1.router import router as api_v1_router
from app.core.config import get_settings
from app.live.service import get_live_store
from app.services.errors import DatasetUnavailableError, NotFoundError, ResultConflictError

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    store = get_live_store()
    task = asyncio.create_task(store.run_forever())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="KROMA API",
    version="1.0.0",
    description=(
        "Мониторинг природных пожаров. Интерактивная документация содержит рабочие "
        "примеры подготовленного пространственно-временного анализа и экспортов."
    ),
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(NotFoundError)
def handle_not_found(_: Request, error: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": str(error), "code": "not_found", "message": str(error)},
    )


@app.exception_handler(DatasetUnavailableError)
def handle_dataset_unavailable(_: Request, error: DatasetUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": str(error), "code": "dataset_unavailable", "message": str(error)},
    )


@app.exception_handler(ResultConflictError)
def handle_result_conflict(_: Request, error: ResultConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": str(error), "code": "result_conflict", "message": str(error)},
    )


app.include_router(health_router)
app.include_router(api_v1_router)
