from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from models import ExceptionReason, ReviewStatus, TransactionResult
from runtime import (
    current_queue,
    current_results,
    get_transaction,
    process_all,
    statement_path,
)
from settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    process_all()
    yield


app = FastAPI(
    title="RedThread Ledger",
    description="Evidence-linked bank statement processing for private-market fund operations.",
    version="0.1.0",
    lifespan=lifespan,
)

_origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == ["*"] else _origins,
    allow_credentials=False if _origins == ["*"] else True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "transactions": len(current_results()),
    }


@app.post("/process")
def run_process() -> dict:
    results = process_all()
    return {"count": len(results)}


def _counts(items: list[TransactionResult]) -> dict[str, int]:
    counts = {
        "ready_to_post": 0,
        "needs_review": 0,
        **{reason.value: 0 for reason in ExceptionReason},
    }
    for item in items:
        if item.status == ReviewStatus.READY_TO_POST:
            counts["ready_to_post"] += 1
        else:
            counts["needs_review"] += 1
        for reason in item.exception_reasons:
            counts[reason.value] += 1
    return counts


@app.get("/queue")
def get_queue() -> dict:
    grouped = current_queue()
    items = current_results()
    return {
        "ready_to_post": grouped["ready_to_post"],
        "needs_review": grouped["needs_review"],
        "counts": _counts(items),
        "total": len(items),
    }


@app.get("/transactions/{transaction_id:path}")
def read_transaction(transaction_id: str) -> TransactionResult:
    item = get_transaction(transaction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return item


@app.get("/statements/{name}")
def read_statement(name: str) -> FileResponse:
    path = statement_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Statement not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


_static = Path(settings.static_dir) if settings.static_dir else Path("frontend/dist")
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="ui")
