"""
FastAPI application entrypoint.

Responsibility:
- Instantiate the FastAPI app.
- Configure CORS so the Vite frontend (localhost:5173 or VITE origin) can call the API.
- Mount the research, copilot, documents, and auth routers.
- Wire up startup/shutdown hooks (e.g. checkpointer/db init) if needed.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.graph.runtime import start_graph_runtime, stop_graph_runtime
from backend.routers import auth, chat, copilot, documents, research

# TODO: read allowed origins from config instead of hardcoding
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the PostgreSQL-checkpointed graph for this application process."""
    await start_graph_runtime()
    try:
        yield
    finally:
        await stop_graph_runtime()


app = FastAPI(title="Research Assistant API", lifespan=lifespan)

# TODO: restrict allow_origins to the actual frontend origin(s) from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(research.router)
app.include_router(copilot.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(chat.router)


@app.get("/health")
async def health() -> dict:
    # TODO: expand with real readiness checks (db, llm client, etc.)
    return {"status": "ok"}
