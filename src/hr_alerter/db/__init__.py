"""Database sub-package for the hr-alerter project.

Exports the core database functions so that other modules can import
them directly from ``hr_alerter.db``:

    from hr_alerter.db import get_connection, init_db, insert_jobs
"""

from hr_alerter.db.manager import get_connection, init_db, insert_jobs

__all__ = ["get_connection", "init_db", "insert_jobs"]
