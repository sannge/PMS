"""Alembic environment configuration for database migrations.

This module configures Alembic to work with our SQLAlchemy models
and SQL Server database connection.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add the project root to the Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import our application's database configuration
from app.database import DATABASE_URL, Base

# Import all models to ensure they are registered with Base.metadata
# This is required for autogenerate to detect all tables
from app.models import (
    Application,
    Attachment,
    Note,
    Notification,
    Project,
    Task,
    User,
)

# Alembic Config object - provides access to .ini file values
config = context.config

# Interpret the config file for Python logging
# This line sets up loggers basically
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from our application config
# This overrides the dummy URL in alembic.ini
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Target metadata for 'autogenerate' support
# This tells Alembic what tables/columns should exist
target_metadata = Base.metadata

# Additional configuration options
# exclude_tables: tables to ignore during autogenerate
# include_schemas: whether to include schema names
# version_table_schema: schema for the alembic_version table


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQL Server specific options
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Enable autogenerate type comparison
            compare_type=True,
            # Enable server default comparison
            compare_server_default=True,
            # Include object names in migrations
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


def include_object(object, name, type_, reflected, compare_to):
    """Filter which database objects to include in autogenerate.

    This function is called for each database object during autogenerate.
    Return True to include the object, False to exclude it.

    Args:
        object: The SQLAlchemy schema object
        name: The name of the object
        type_: The type of object ('table', 'column', 'index', etc.)
        reflected: True if the object was reflected from the database
        compare_to: The object being compared to (for type_='column')

    Returns:
        bool: True to include the object in migrations
    """
    # Exclude system tables and internal tables
    if type_ == "table":
        # Exclude SQL Server system tables
        if name.startswith("sys") or name.startswith("INFORMATION_SCHEMA"):
            return False
        # Exclude trace/extended events tables
        if name.startswith("trace_") or name.startswith("queue_"):
            return False

    return True


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
