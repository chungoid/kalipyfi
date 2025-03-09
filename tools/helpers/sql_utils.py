from pathlib import Path

from database.db_manager import get_db_connection
from tools.hcxtool.db import get_founds


def get_founds_from_hcxtool(basedir: Path) -> list:
    """
    Opens a database connection using the provided basedir and returns all found keys
    from the hcxtool table.

    Parameters:
        basedir (Path): The base directory (typically your project BASE_DIR).

    Returns:
        list: A list of tuples representing the found records.
    """
    conn = get_db_connection(basedir)
    try:
        founds = get_founds(conn)
        return founds
    finally:
        conn.close()