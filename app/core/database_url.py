"""Database URL conversion for synchronous migration engines."""

from sqlalchemy.engine import URL, make_url


def build_sync_database_url(database_url: str) -> URL:
    """Select a supported sync driver without changing connection fields."""
    parsed_url = make_url(database_url)
    backend_name = parsed_url.get_backend_name()
    if backend_name == "postgresql":
        return parsed_url.set(drivername="postgresql+psycopg")
    if backend_name == "sqlite":
        return parsed_url.set(drivername="sqlite")
    raise ValueError("Migration database backend must be postgresql or sqlite")
