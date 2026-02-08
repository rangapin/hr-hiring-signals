"""pypyr step: initialize the SQLite database.

Reads ``db_path`` from the pypyr context (defaulting to
``./data/hr_alerter.db``), opens a connection, runs the schema
migration, and stores the live connection back into the context so
that downstream steps can reuse it.

Usage in a pipeline YAML::

    steps:
      - name: hr_alerter.steps.db_init

Context keys consumed:
    db_path (str, optional): Path to the SQLite database file.

Context keys produced:
    conn (sqlite3.Connection): The initialised database connection.
    db_path (str): The resolved database path (written back so later
        steps can see the default that was applied).
"""

import logging
import os
import pathlib

from hr_alerter.db.manager import get_connection, init_db

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join("data", "hr_alerter.db")


def run_step(context: dict) -> None:
    """pypyr entry-point: open DB connection and initialise schema.

    Args:
        context: The mutable pypyr context dictionary.
    """
    db_path: str = context.get("db_path", DEFAULT_DB_PATH)

    # Ensure the parent directory exists for file-based databases.
    if db_path != ":memory:":
        parent = pathlib.Path(db_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        logger.info("Database directory ensured: %s", parent)

    conn = get_connection(db_path)
    init_db(conn)

    context["conn"] = conn
    context["db_path"] = db_path

    logger.info("Database initialised at %s", db_path)
