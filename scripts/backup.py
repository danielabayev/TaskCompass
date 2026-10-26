"""Export the whole database to one SQL file, or restore from one.

    python -m scripts.backup                       # -> backups/task_compass-YYYYMMDD-HHMMSS.sql
    python -m scripts.backup --restore FILE        # replaces the current data with FILE

By default pg_dump / psql run inside the Docker container, so nothing has to
be installed on Windows. With --local they run from PATH instead.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from task_compass import config  # noqa: F401  (loads .env)

BACKUP_DIR = Path("backups")


def _command(tool: str, local: bool, *args: str) -> list[str]:
    user, db = os.environ.get("POSTGRES_USER", "task_compass"), os.environ.get("POSTGRES_DB", "task_compass")
    if local:
        host, port = os.environ.get("POSTGRES_HOST", "localhost"), os.environ.get("POSTGRES_PORT", "5433")
        return [tool, "-h", host, "-p", port, "-U", user, "-d", db, *args]
    return ["docker", "compose", "exec", "-T", "db", tool, "-U", user, "-d", db, *args]


def _env() -> dict:
    return {**os.environ, "PGPASSWORD": os.environ.get("POSTGRES_PASSWORD", "")}


def backup(local: bool) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"task_compass-{datetime.now():%Y%m%d-%H%M%S}.sql"
    # --clean --if-exists: the file drops and recreates every object, so a
    # restore gives exactly the state at backup time.
    with target.open("wb") as out:
        subprocess.run(_command("pg_dump", local, "--clean", "--if-exists", "--no-owner"),
                       stdout=out, check=True, env=_env())
    return target


def restore(path: Path, local: bool) -> None:
    with path.open("rb") as source:
        subprocess.run(_command("psql", local, "-v", "ON_ERROR_STOP=1", "-q"),
                       stdin=source, stdout=subprocess.DEVNULL, check=True, env=_env())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--restore", type=Path, metavar="FILE")
    parser.add_argument("--local", action="store_true", help="use pg_dump/psql from PATH, not Docker")
    args = parser.parse_args()
    try:
        if args.restore:
            restore(args.restore, args.local)
            print(f"restored {args.restore}")
        else:
            print(f"saved {backup(args.local)}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
