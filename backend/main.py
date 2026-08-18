"""
FastAPI application entrypoint.

Responsibility:
- Instantiate the FastAPI app.
- Configure CORS so the Vite frontend (localhost:5173 or VITE origin) can call the API.
- Mount the search, selection, and chat routers.
- Wire up startup/shutdown hooks (e.g. checkpointer/db init) if needed.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import search, selection, chat

# TODO: read allowed origins from config instead of hardcoding
settings = get_settings()

app = FastAPI(title="Research Assistant API")

# TODO: restrict allow_origins to the actual frontend origin(s) from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: mount routers once implemented
app.include_router(search.router)
app.include_router(selection.router)
app.include_router(chat.router)


@app.get("/health")
async def health() -> dict:
    # TODO: expand with real readiness checks (db, llm client, etc.)
    return {"status": "ok"}
