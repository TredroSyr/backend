#!/usr/bin/env python
"""Wait for PostgreSQL, then exec the container command."""

from __future__ import annotations

import os
import sys
import time

import psycopg


def wait_for_postgres(timeout_seconds: int = 60) -> None:
    host = os.environ.get("DATABASE_HOST", "postgres")
    port = int(os.environ.get("DATABASE_PORT", "5432"))
    user = os.environ.get("DATABASE_USER", "tredro")
    password = os.environ.get("DATABASE_PASSWORD", "tredro")
    dbname = os.environ.get("DATABASE_NAME", "tredro")

    deadline = time.time() + timeout_seconds
    while True:
        try:
            with psycopg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                connect_timeout=3,
            ) as conn:
                conn.execute("SELECT 1")
            print(f"PostgreSQL is available at {host}:{port}", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 - retry until timeout
            if time.time() >= deadline:
                print(f"Timed out waiting for PostgreSQL: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"Waiting for PostgreSQL at {host}:{port}...", flush=True)
            time.sleep(1)


def main() -> None:
    wait_for_postgres()
    if len(sys.argv) < 2:
        print("No command provided to entrypoint.", file=sys.stderr)
        sys.exit(1)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
