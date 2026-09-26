"""Run the API server:

    python -m backend.serve [--host 127.0.0.1] [--port 8001] [--reload]

Use this instead of calling `uvicorn backend.main:app` directly. On Windows,
uvicorn's default event loop (ProactorEventLoop, used whenever it is *not*
reloading or running workers) cannot run psycopg's async mode, so every
database call -- the Postgres pool, thread metadata, reports, documents, chat
history, the LangGraph checkpointer -- fails with "Psycopg cannot use the
'ProactorEventLoop' to run in async mode". This launcher tells uvicorn to
use a selector loop there (custom loop factories need uvicorn >= 0.36). On
other platforms it changes nothing.
"""

import argparse
import asyncio
import sys
from typing import Optional, Sequence

import uvicorn

APP = "backend.main:app"


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """The loop factory uvicorn is pointed at on Windows (see module docstring)."""
    return asyncio.SelectorEventLoop()


def loop_setting() -> str:
    """uvicorn's `loop` option: our selector loop on Windows, its own choice elsewhere."""
    return "backend.serve:selector_loop_factory" if sys.platform == "win32" else "auto"


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Nexora API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args(argv)

    uvicorn.run(APP, host=args.host, port=args.port, reload=args.reload, loop=loop_setting())


if __name__ == "__main__":
    main()
