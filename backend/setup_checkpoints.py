"""Explicit setup command for LangGraph's PostgreSQL checkpoint tables."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence

from backend.graph.checkpoint import PostgresCheckpointResource


CHECKPOINT_DATABASE_URL_ENV = "CHECKPOINT_DATABASE_URL"


async def setup_checkpoint_schema(database_url: str, schema: str) -> None:
    """Run LangGraph-owned migrations in one explicit checkpoint schema."""
    resource = PostgresCheckpointResource(
        database_url,
        checkpoint_schema=schema,
        min_size=1,
        max_size=1,
    )
    try:
        await resource.open()
        await resource.saver.setup()
    finally:
        await resource.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up LangGraph checkpoint tables in an existing PostgreSQL schema."
    )
    parser.add_argument(
        "--schema",
        required=True,
        help="Existing dedicated schema that will contain LangGraph checkpoint tables.",
    )
    return parser


def _run_setup(database_url: str, schema: str) -> None:
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(setup_checkpoint_schema(database_url, schema))


def main(argv: Sequence[str] | None = None) -> int:
    """Run explicit setup, returning a shell-compatible status code."""
    parser = _parser()
    args = parser.parse_args(argv)
    database_url = os.environ.get(CHECKPOINT_DATABASE_URL_ENV)
    if not database_url:
        parser.error(
            f"{CHECKPOINT_DATABASE_URL_ENV} must be explicitly set; "
            "DATABASE_URL is never used as a fallback."
        )

    try:
        _run_setup(database_url, args.schema)
    except Exception as exc:
        print(
            f"Checkpoint setup failed ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1

    print(f"LangGraph checkpoint schema is ready: {args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
