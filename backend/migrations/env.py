import logging
from collections import Counter
from logging.config import fileConfig

from flask import current_app

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def get_engine():
    try:
        # Flask-SQLAlchemy >= 3 exposes the engine as a property.
        return current_app.extensions['migrate'].db.engine
    except (TypeError, AttributeError):
        # Compatibility with Flask-SQLAlchemy < 3 and Alchemical.
        return current_app.extensions['migrate'].db.get_engine()


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_metadata():
    if hasattr(target_db, 'metadatas'):
        return target_db.metadatas[None]
    return target_db.metadata


def _sqlite_foreign_key_violations(connection):
    """Return FK violations keyed by relationship rather than SQLite fkid."""
    violations = Counter()
    foreign_keys_by_table = {}
    preparer = connection.dialect.identifier_preparer

    for table_name, row_id, parent_table, foreign_key_id in (
        connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    ):
        if table_name not in foreign_keys_by_table:
            quoted_table = preparer.quote(table_name)
            foreign_keys_by_table[table_name] = connection.exec_driver_sql(
                f"PRAGMA foreign_key_list({quoted_table})"
            ).all()

        relationship = tuple(
            (row[3], row[4])
            for row in sorted(
                (
                    row
                    for row in foreign_keys_by_table[table_name]
                    if row[0] == foreign_key_id
                ),
                key=lambda row: row[1],
            )
        )
        violations[(table_name, row_id, parent_table, relationship)] += 1

    return violations


def run_migrations_offline():
    """Reject SQL-only generation because adoption requires live inspection."""
    raise RuntimeError(
        "Offline Alembic SQL generation is unsupported for this adoption "
        "migration chain. Run the online migration against an isolated "
        "database copy after reviewing a verified backup."
    )


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()

    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        existing_foreign_key_violations = Counter()
        restore_sqlite_foreign_keys = False
        migration_error = None
        try:
            if is_sqlite:
                existing_foreign_key_violations = (
                    _sqlite_foreign_key_violations(connection)
                )
                if existing_foreign_key_violations:
                    logger.warning(
                        "SQLite database has %s pre-existing foreign key "
                        "violation(s); they will be preserved and no new "
                        "violations are allowed",
                        sum(existing_foreign_key_violations.values()),
                    )

                # SQLite batch migrations rebuild tables. Parent tables cannot
                # be replaced while populated child tables enforce foreign keys.
                if connection.in_transaction():
                    connection.rollback()
                restore_sqlite_foreign_keys = True
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                foreign_keys_enabled = connection.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar()
                connection.commit()
                if foreign_keys_enabled != 0:
                    raise RuntimeError(
                        "Could not disable SQLite foreign keys for batch migration"
                    )

                # Pysqlite does not reliably begin a DBAPI transaction for DDL.
                # An explicit outer transaction makes the full upgrade command,
                # including its final integrity check, atomic.
                connection.exec_driver_sql("BEGIN IMMEDIATE")

            context.configure(
                connection=connection,
                target_metadata=get_metadata(),
                **conf_args
            )

            with context.begin_transaction():
                context.run_migrations()

            if is_sqlite:
                migrated_foreign_key_violations = (
                    _sqlite_foreign_key_violations(connection)
                )
                new_violations = (
                    migrated_foreign_key_violations
                    - existing_foreign_key_violations
                )
                if new_violations:
                    raise RuntimeError(
                        "SQLite migration introduced "
                        f"{sum(new_violations.values())} new foreign key "
                        "violation(s)"
                    )
                connection.commit()
        except BaseException as error:
            migration_error = error
            if is_sqlite and connection.in_transaction():
                try:
                    connection.rollback()
                except Exception:
                    logger.exception(
                        "Failed to roll back SQLite migration transaction"
                    )
                    connection.invalidate()
            raise
        finally:
            if restore_sqlite_foreign_keys:
                try:
                    if connection.in_transaction():
                        connection.rollback()
                    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                    foreign_keys_enabled = connection.exec_driver_sql(
                        "PRAGMA foreign_keys"
                    ).scalar()
                    connection.commit()
                    if foreign_keys_enabled != 1:
                        raise RuntimeError(
                            "Could not restore SQLite foreign key enforcement"
                        )
                except Exception:
                    connection.invalidate()
                    if migration_error is None:
                        raise
                    logger.exception(
                        "Failed to restore SQLite foreign keys; invalidated "
                        "the migration connection"
                    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
