import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app import models  # noqa: F401  register all mapped classes
from app.config import get_settings
from app.db import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url", f"sqlite+aiosqlite:///{get_settings().database_path}"
)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


_ALEMBIC_ABANDONED_MESSAGE = (
    "Alembic's revision chain is not current with app.models and is not "
    "how this project actually bootstraps a database's schema. Running "
    "`alembic upgrade head` against an empty database produces a schema "
    "4 tables and 17+ columns short of what models.py/the running app "
    "requires -- reproduced empirically in "
    "docs/audit/04_schema_migrations.md. The real bootstrap path is "
    "app.db.create_all() (via app.db.run_cli, main.py's FastAPI "
    "lifespan, or `python -m app.seed`), which stays current with "
    "app.models directly and is what every other entry point in this "
    "codebase actually calls. Refusing here rather than silently handing "
    "you a schema that looks migrated but isn't -- that is strictly "
    "worse than an obvious, immediate failure. If someone has committed "
    "to reviving the Alembic chain (regenerating it from current models "
    "so it is genuinely current again), set REPAIRFLOW_ALLOW_ALEMBIC=1 "
    "to bypass this guard; that also gates `alembic revision "
    "--autogenerate`, `alembic current`, and every other command that "
    "reaches this point."
)


def _require_alembic_opt_in() -> None:
    if os.environ.get("REPAIRFLOW_ALLOW_ALEMBIC") != "1":
        raise RuntimeError(_ALEMBIC_ABANDONED_MESSAGE)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


_require_alembic_opt_in()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
