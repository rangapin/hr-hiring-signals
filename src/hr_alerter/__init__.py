"""hr-alerter: Monitor Polish job boards for HR hiring activity."""

__version__ = "0.1.0"

import os
import pathlib

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".hr-alerter", "hr_alerter.db"
)

PACKAGE_DIR = pathlib.Path(__file__).parent
