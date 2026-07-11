"""Safe Flask-Migrate application entry point.

Run from the repository root with the target database URI configured:

    python -m flask --app backend.migration_app:create_app \
        db -d backend/migrations upgrade

This factory deliberately skips runtime schema synchronization, startup data
repairs, and schedulers so Alembic is the only schema writer.
"""


def create_app():
    from backend.app import create_migration_app

    return create_migration_app()
