"""Production database commands shared by source and packaged entry points."""

import argparse
import hashlib
import json
import logging
import re
import stat
import sys
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import inspect as sqlalchemy_inspect, text
from sqlalchemy.engine import make_url


BACKUP_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
BACKUP_MANIFEST_SCHEMA_VERSION = 2
BACKUP_MANIFEST_SUFFIX = ".manifest.json"
MAX_BACKUP_MANIFEST_BYTES = 1024 * 1024
MAX_BACKUP_SQL_BYTES = 1024 * 1024 * 1024 * 1024
MAX_BACKUP_COMPRESSION_RATIO = 1000
DEFAULT_MIGRATION_BACKUP_MAX_AGE_MINUTES = 60
MAX_MIGRATION_BACKUP_AGE_MINUTES = 24 * 60


class ProductionDatabaseBlocked(RuntimeError):
    retryable = False

    def __init__(self, message, *, report=None):
        super().__init__(message)
        self.report = report


class ProductionDatabaseUnavailable(ProductionDatabaseBlocked):
    """A preflight availability failure that the server restart loop may retry."""

    retryable = True


def _migrations_directory() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    candidates = (
        bundle_root / "backend" / "migrations",
        Path(__file__).resolve().parent / "migrations",
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])


def _safe_database_url(uri: str) -> str:
    return make_url(uri).set(query={}).render_as_string(hide_password=True)


def database_target_identity(uri: str, *, unix_socket=None) -> str:
    """Return a stable MySQL target identity without credentials or URL options."""
    url = make_url(uri)
    if not url.drivername.startswith("mysql") or not url.database:
        raise RuntimeError("Backup target identity requires a MySQL database URL")
    host = (url.host or "localhost").strip().lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    identity = f"mysql://{host}:{url.port or 3306}/{quote(url.database, safe='')}"
    socket_path = unix_socket or url.query.get("unix_socket")
    if socket_path:
        socket_fingerprint = hashlib.sha256(str(socket_path).encode("utf-8")).hexdigest()
        identity += f"?unix_socket_sha256={socket_fingerprint}"
    return identity


def _canonical_server_uuid(value) -> str:
    try:
        return str(UUID(str(value).strip()))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError("MySQL server_uuid is missing or invalid") from exc


def _gtid_digest(value) -> str | None:
    normalized = "".join(str(value or "").split())
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_mysql_target_state(connection) -> dict:
    """Read target identity and schema state without requiring elevated grants."""
    server_uuid = _canonical_server_uuid(
        connection.execute(text("SELECT @@server_uuid")).scalar_one()
    )
    inspector = sqlalchemy_inspect(connection)
    if inspector.has_table("alembic_version"):
        raw_heads = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars()
        heads = sorted({str(value).strip() for value in raw_heads if str(value).strip()})
    else:
        heads = []

    gtid_value = connection.execute(
        text("SELECT @@GLOBAL.gtid_executed")
    ).scalar_one()
    return {
        "server_uuid": server_uuid,
        "alembic_heads": heads,
        "gtid_executed_sha256": _gtid_digest(gtid_value),
    }


def backup_state_manifest_fields(before: dict, after: dict) -> dict:
    """Require stable instance/schema state across mysqldump and bind the result."""
    if before.get("server_uuid") != after.get("server_uuid"):
        raise RuntimeError("MySQL server_uuid changed while the backup was running")
    if before.get("alembic_heads") != after.get("alembic_heads"):
        raise RuntimeError("Alembic heads changed while the backup was running")
    before_gtid = before.get("gtid_executed_sha256")
    after_gtid = after.get("gtid_executed_sha256")
    if bool(before_gtid) != bool(after_gtid):
        raise RuntimeError("MySQL GTID availability changed while the backup was running")
    if before_gtid and before_gtid != after_gtid:
        raise RuntimeError(
            "MySQL GTID state changed while the backup was running; stop all writes "
            "and take a new backup"
        )
    return {
        "server_uuid": _canonical_server_uuid(after.get("server_uuid")),
        "alembic_heads": list(after.get("alembic_heads") or []),
        "gtid_executed_sha256": after_gtid,
        "gtid_check": "unchanged" if after_gtid else "unavailable",
        "requires_write_quiescence": True,
    }


def verify_backup_target_state(manifest: dict, current_state: dict) -> None:
    if manifest["server_uuid"] != _canonical_server_uuid(
        current_state.get("server_uuid")
    ):
        raise RuntimeError(
            "Backup server_uuid does not match the current MySQL instance; no DDL was attempted"
        )
    current_heads = sorted(set(current_state.get("alembic_heads") or []))
    if manifest["alembic_heads"] != current_heads:
        raise RuntimeError(
            "Backup Alembic heads do not match the current database; no DDL was attempted"
        )
    expected_gtid = manifest.get("gtid_executed_sha256")
    current_gtid = current_state.get("gtid_executed_sha256")
    if expected_gtid:
        if not current_gtid or expected_gtid.lower() != str(current_gtid).lower():
            raise RuntimeError(
                "MySQL GTID state changed after the backup; stop writes and take a new "
                "backup before migration"
            )
    else:
        logging.getLogger(__name__).warning(
            "Backup has no GTID marker. Automatic write-quiescence verification is "
            "unavailable; all application writes must remain stopped until migration completes."
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_manifest_path(backup_file) -> Path:
    return Path(f"{Path(backup_file)}{BACKUP_MANIFEST_SUFFIX}")


def _parse_backup_manifest(payload: bytes) -> dict:
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Backup manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError("Backup manifest must contain a JSON object")
    schema_version = manifest.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != BACKUP_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"Backup manifest schema_version must be {BACKUP_MANIFEST_SCHEMA_VERSION}"
        )
    expected_digest = manifest.get("sha256")
    if not isinstance(expected_digest, str) or not BACKUP_SHA256_RE.fullmatch(
        expected_digest
    ):
        raise RuntimeError("Backup manifest sha256 must be a 64-character digest")
    expected_size = manifest.get("size_bytes")
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size <= 0
    ):
        raise RuntimeError("Backup manifest size_bytes must be a positive integer")
    created_at = manifest.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        raise RuntimeError("Backup manifest created_at must be an explicit UTC timestamp")
    manifest["server_uuid"] = _canonical_server_uuid(manifest.get("server_uuid"))
    heads = manifest.get("alembic_heads")
    if (
        not isinstance(heads, list)
        or any(
            not isinstance(head, str)
            or not head.strip()
            or len(head.strip()) > 128
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", head.strip())
            for head in heads
        )
    ):
        raise RuntimeError("Backup manifest alembic_heads must be a list of revision IDs")
    normalized_heads = sorted({head.strip() for head in heads})
    if len(normalized_heads) != len(heads) or heads != normalized_heads:
        raise RuntimeError("Backup manifest alembic_heads must be unique and sorted")
    manifest["alembic_heads"] = normalized_heads
    gtid_digest = manifest.get("gtid_executed_sha256")
    if gtid_digest is not None and (
        not isinstance(gtid_digest, str) or not BACKUP_SHA256_RE.fullmatch(gtid_digest)
    ):
        raise RuntimeError(
            "Backup manifest gtid_executed_sha256 must be null or a SHA-256 digest"
        )
    if isinstance(gtid_digest, str):
        manifest["gtid_executed_sha256"] = gtid_digest.lower()
    gtid_check = manifest.get("gtid_check")
    if gtid_check not in {"unchanged", "unavailable"}:
        raise RuntimeError("Backup manifest gtid_check is invalid")
    if (gtid_check == "unchanged") != bool(gtid_digest):
        raise RuntimeError("Backup manifest GTID marker and gtid_check are inconsistent")
    if manifest.get("requires_write_quiescence") is not True:
        raise RuntimeError("Backup manifest must require write quiescence")
    return manifest


def _verify_manifest_freshness(
    manifest: dict,
    *,
    max_age_minutes: int,
    now: datetime | None = None,
) -> None:
    if (
        isinstance(max_age_minutes, bool)
        or not isinstance(max_age_minutes, int)
        or not 1 <= max_age_minutes <= MAX_MIGRATION_BACKUP_AGE_MINUTES
    ):
        raise RuntimeError(
            "Migration backup maximum age must be between 1 and "
            f"{MAX_MIGRATION_BACKUP_AGE_MINUTES} minutes"
        )
    raw_created_at = manifest["created_at"].strip()
    try:
        created_at = datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("Backup manifest created_at is not a valid timestamp") from exc
    if created_at.tzinfo is None or created_at.utcoffset() != timedelta(0):
        raise RuntimeError("Backup manifest created_at must use UTC")
    reference_time = now or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        raise RuntimeError("Backup freshness reference time must include a timezone")
    reference_time = reference_time.astimezone(timezone.utc)
    created_at = created_at.astimezone(timezone.utc)
    if created_at > reference_time:
        raise RuntimeError(
            "Backup manifest created_at is in the future; correct clock skew and take a new backup"
        )
    if reference_time - created_at > timedelta(minutes=max_age_minutes):
        raise RuntimeError(
            f"Backup is older than the allowed {max_age_minutes} minutes; take a new backup"
        )


def _verify_manifest_content(
    manifest: dict,
    *,
    actual_size: int,
    actual_digest: str,
    expected_target: str,
) -> None:
    expected_size = manifest["size_bytes"]

    if actual_size != expected_size:
        raise RuntimeError(
            f"Backup size mismatch: manifest={expected_size}, actual={actual_size}"
        )
    expected_digest = manifest["sha256"]
    if actual_digest.lower() != expected_digest.lower():
        raise RuntimeError("Backup SHA-256 mismatch; the backup file may be incomplete")
    if manifest.get("database_target") != expected_target:
        raise RuntimeError(
            "Backup database_target does not match the configured migration target"
        )


def _verify_external_backup(
    backup_path: Path,
    database_uri: str,
    *,
    unix_socket=None,
    max_age_minutes: int,
    now: datetime | None,
) -> dict:
    manifest_path = backup_manifest_path(backup_path)
    if not manifest_path.is_file():
        raise RuntimeError(
            f"Backup manifest does not exist: {manifest_path}. Keep the downloaded "
            "backup and .manifest.json sidecar together."
        )
    if manifest_path.stat().st_size > MAX_BACKUP_MANIFEST_BYTES:
        raise RuntimeError("Backup manifest is unexpectedly large")
    try:
        with manifest_path.open("rb") as manifest_stream:
            manifest_payload = manifest_stream.read(MAX_BACKUP_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise RuntimeError("Backup manifest could not be read") from exc
    if len(manifest_payload) > MAX_BACKUP_MANIFEST_BYTES:
        raise RuntimeError("Backup manifest is unexpectedly large")
    manifest = _parse_backup_manifest(manifest_payload)
    _verify_manifest_freshness(
        manifest,
        max_age_minutes=max_age_minutes,
        now=now,
    )

    actual_size = backup_path.stat().st_size
    actual_digest = _file_sha256(backup_path)
    _verify_manifest_content(
        manifest,
        actual_size=actual_size,
        actual_digest=actual_digest,
        expected_target=database_target_identity(database_uri, unix_socket=unix_socket),
    )
    return {
        **manifest,
        "sha256": actual_digest,
        "size_bytes": actual_size,
        "backup_path": str(backup_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
    }


def _safe_zip_entry(info: zipfile.ZipInfo) -> bool:
    name = info.filename
    if (
        not name
        or len(name) > 255
        or "/" in name
        or "\\" in name
        or ":" in name
        or any(ord(character) < 32 for character in name)
        or info.is_dir()
        or info.flag_bits & 0x1
    ):
        return False
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    return not unix_mode or not stat.S_ISLNK(unix_mode)


def _verify_zip_ratio(info: zipfile.ZipInfo) -> None:
    if info.file_size > MAX_BACKUP_SQL_BYTES:
        raise RuntimeError("Backup ZIP SQL entry is unexpectedly large")
    if info.file_size and not info.compress_size:
        raise RuntimeError("Backup ZIP entry has an invalid compressed size")
    if (
        info.file_size > MAX_BACKUP_MANIFEST_BYTES
        and info.file_size > info.compress_size * MAX_BACKUP_COMPRESSION_RATIO
    ):
        raise RuntimeError("Backup ZIP entry has an unsafe compression ratio")


def _verify_backup_zip(
    backup_path: Path,
    database_uri: str,
    *,
    unix_socket=None,
    max_age_minutes: int,
    now: datetime | None,
) -> dict:
    try:
        with zipfile.ZipFile(backup_path, "r") as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) != 2:
                raise RuntimeError("Backup ZIP must contain exactly one SQL and one manifest")
            if len({name.casefold() for name in names}) != len(names):
                raise RuntimeError("Backup ZIP contains duplicate entry names")
            if archive.comment:
                raise RuntimeError("Backup ZIP comments are not allowed")
            if not all(_safe_zip_entry(entry) for entry in entries):
                raise RuntimeError("Backup ZIP contains an unsafe entry")

            sql_entries = [
                entry for entry in entries if entry.filename.lower().endswith(".sql")
            ]
            if len(sql_entries) != 1:
                raise RuntimeError("Backup ZIP must contain exactly one SQL entry")
            sql_info = sql_entries[0]
            manifest_name = f"{sql_info.filename}{BACKUP_MANIFEST_SUFFIX}"
            manifest_entries = [
                entry for entry in entries if entry.filename == manifest_name
            ]
            if len(manifest_entries) != 1:
                raise RuntimeError(
                    "Backup ZIP manifest name must match <backup.sql>.manifest.json"
                )
            manifest_info = manifest_entries[0]
            if manifest_info.file_size > MAX_BACKUP_MANIFEST_BYTES:
                raise RuntimeError("Backup manifest is unexpectedly large")
            _verify_zip_ratio(sql_info)

            with archive.open(manifest_info, "r") as manifest_stream:
                manifest_payload = manifest_stream.read(MAX_BACKUP_MANIFEST_BYTES + 1)
            if len(manifest_payload) > MAX_BACKUP_MANIFEST_BYTES:
                raise RuntimeError("Backup manifest is unexpectedly large")
            manifest = _parse_backup_manifest(manifest_payload)
            _verify_manifest_freshness(
                manifest,
                max_age_minutes=max_age_minutes,
                now=now,
            )
            if manifest.get("backup_filename") != sql_info.filename:
                raise RuntimeError(
                    "Backup ZIP manifest backup_filename does not match its SQL entry"
                )

            digest = hashlib.sha256()
            actual_size = 0
            with archive.open(sql_info, "r") as sql_stream:
                for chunk in iter(lambda: sql_stream.read(1024 * 1024), b""):
                    actual_size += len(chunk)
                    if actual_size > manifest["size_bytes"]:
                        raise RuntimeError(
                            "Backup size exceeds the size declared by its manifest"
                        )
                    digest.update(chunk)
            actual_digest = digest.hexdigest()
            _verify_manifest_content(
                manifest,
                actual_size=actual_size,
                actual_digest=actual_digest,
                expected_target=database_target_identity(
                    database_uri, unix_socket=unix_socket
                ),
            )
    except RuntimeError:
        raise
    except (
        OSError,
        EOFError,
        NotImplementedError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        zlib.error,
    ) as exc:
        raise RuntimeError("Backup ZIP could not be safely verified") from exc

    return {
        **manifest,
        "sha256": actual_digest,
        "size_bytes": actual_size,
        "backup_path": str(backup_path.resolve()),
        "manifest_path": f"{backup_path.resolve()}!/{manifest_name}",
        "archive_entry": sql_info.filename,
    }


def verify_backup_file(
    backup_file,
    database_uri: str,
    *,
    unix_socket=None,
    max_age_minutes: int = DEFAULT_MIGRATION_BACKUP_MAX_AGE_MINUTES,
    now: datetime | None = None,
) -> dict:
    """Verify a ZIP bundle or a backup with an adjacent target-bound manifest."""
    backup_path = Path(backup_file).expanduser()
    if not backup_path.is_file():
        raise RuntimeError(f"Backup file does not exist: {backup_path}")
    if backup_path.suffix.lower() == ".zip" or zipfile.is_zipfile(backup_path):
        return _verify_backup_zip(
            backup_path,
            database_uri,
            unix_socket=unix_socket,
            max_age_minutes=max_age_minutes,
            now=now,
        )
    return _verify_external_backup(
        backup_path,
        database_uri,
        unix_socket=unix_socket,
        max_age_minutes=max_age_minutes,
        now=now,
    )


def inspect_configured_database(
    *,
    deep_checks=True,
    enforce_runtime_least_privilege=True,
):
    from backend.config import Config
    from scripts.check_production_database import inspect_database

    connect_args = Config.SQLALCHEMY_ENGINE_OPTIONS.get("connect_args", {})
    return inspect_database(
        Config.SQLALCHEMY_DATABASE_URI,
        require_tls=bool(Config.DATABASE_REQUIRE_TLS),
        connect_timeout=connect_args.get("connect_timeout", 5),
        read_timeout=connect_args.get("read_timeout", 30),
        write_timeout=connect_args.get("write_timeout", 30),
        query_timeout=getattr(Config, "MYSQL_PREFLIGHT_QUERY_TIMEOUT", 10),
        deep_checks=deep_checks,
        enforce_runtime_least_privilege=enforce_runtime_least_privilege,
        configured_connect_args=connect_args,
    )


def ensure_configured_database_ready(
    *,
    log_report=True,
    deep_checks=None,
    enforce_runtime_least_privilege=True,
):
    from backend.config import Config
    from scripts.check_production_database import format_human_report

    if deep_checks is None:
        deep_checks = bool(Config.PRODUCTION_DATABASE_DEEP_CHECKS_ENABLED)
    report = inspect_configured_database(
        deep_checks=deep_checks,
        enforce_runtime_least_privilege=enforce_runtime_least_privilege,
    )
    rendered = format_human_report(report)
    if log_report:
        for line in rendered.splitlines():
            logging.info("database-preflight: %s", line)
    if report["summary"]["overall"] == "blocked":
        error_class = (
            ProductionDatabaseUnavailable
            if report["summary"].get("retryable")
            else ProductionDatabaseBlocked
        )
        raise error_class(
            "Production database preflight blocked startup; run --check-database "
            "for the complete read-only report",
            report=report,
        )
    return report


def _read_migration_target_state(app) -> dict:
    from backend.app import db

    with app.app_context():
        with db.engine.connect() as connection:
            return read_mysql_target_state(connection)


def migrate_configured_database(*, backup_file: str, confirmed: bool):
    from flask_migrate import upgrade

    from backend.app import _assert_database_at_alembic_head
    from backend.config import Config
    from backend.migration_app import create_app as create_migration_app

    if not confirmed:
        raise RuntimeError("Database migration requires --yes")
    url = make_url(Config.SQLALCHEMY_DATABASE_URI)
    if not url.drivername.startswith("mysql"):
        raise RuntimeError("Packaged production migration is only enabled for MySQL")
    if not backup_file:
        raise RuntimeError("Database migration requires --backup-file")
    connect_args = Config.SQLALCHEMY_ENGINE_OPTIONS.get("connect_args", {})
    configured_socket = getattr(Config, "MYSQL_UNIX_SOCKET", "") or connect_args.get(
        "unix_socket"
    )
    verified_backup = verify_backup_file(
        backup_file,
        Config.SQLALCHEMY_DATABASE_URI,
        unix_socket=configured_socket,
        max_age_minutes=getattr(
            Config,
            "MIGRATION_BACKUP_MAX_AGE_MINUTES",
            DEFAULT_MIGRATION_BACKUP_MAX_AGE_MINUTES,
        ),
    )

    migrations_dir = _migrations_directory()
    if not migrations_dir.is_dir():
        raise RuntimeError(f"Packaged migrations are missing: {migrations_dir}")

    app = create_migration_app()
    try:
        current_state = _read_migration_target_state(app)
    except Exception:
        logging.exception(
            "Could not verify the live MySQL instance before migration for %s",
            _safe_database_url(Config.SQLALCHEMY_DATABASE_URI),
        )
        raise RuntimeError(
            "Database migration could not verify the current MySQL instance; no DDL was attempted"
        ) from None
    verify_backup_target_state(verified_backup, current_state)

    logging.warning(
        "Starting forward-only migration for %s with verified backup %s (SHA-256 %s)",
        _safe_database_url(Config.SQLALCHEMY_DATABASE_URI),
        verified_backup["backup_path"],
        verified_backup["sha256"],
    )
    logging.warning(
        "Application writes must remain stopped until migration and postflight complete"
    )
    try:
        with app.app_context():
            upgrade(directory=str(migrations_dir))
        _assert_database_at_alembic_head(app)
    except (Exception, SystemExit):
        logging.exception(
            "Database migration failed for %s after verifying backup %s",
            _safe_database_url(Config.SQLALCHEMY_DATABASE_URI),
            verified_backup["backup_path"],
        )
        raise RuntimeError(
            "Database migration failed. Do not downgrade; restore the verified "
            "backup into an isolated database before changing the connection target."
        ) from None

    return ensure_configured_database_ready(
        log_report=True,
        deep_checks=True,
        enforce_runtime_least_privilege=False,
    )


def build_parser():
    parser = argparse.ArgumentParser(add_help=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-database",
        action="store_true",
        help="run read-only production database checks and exit",
    )
    mode.add_argument(
        "--migrate-database",
        action="store_true",
        help="run the packaged forward-only Alembic migration and exit",
    )
    mode.add_argument(
        "--import-sqlite",
        metavar="PATH",
        help="preflight or import a SQLite database into the configured MySQL target",
    )
    parser.add_argument("--json", action="store_true", help="emit check report as JSON")
    parser.add_argument(
        "--backup-file",
        default="",
        metavar="PATH",
        help="backup ZIP bundle or SQL file with an adjacent .manifest.json sidecar",
    )
    parser.add_argument("--yes", action="store_true", help="confirm database migration")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="execute --import-sqlite after a successful dry-run",
    )
    parser.add_argument(
        "--expected-source-sha256",
        default="",
        help="source snapshot digest printed by the SQLite import dry-run",
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000, help="SQLite import rows per batch"
    )
    return parser


def execute_cli(argv=None):
    """Execute an explicit database command, or return None to start the server."""
    args = build_parser().parse_args(argv)
    if not args.check_database and not args.migrate_database and not args.import_sqlite:
        if (
            args.json
            or args.backup_file
            or args.yes
            or args.execute
            or args.expected_source_sha256
            or args.batch_size != 1000
        ):
            raise RuntimeError("Database command flags require an explicit command mode")
        return None

    if args.check_database:
        if (
            args.backup_file
            or args.yes
            or args.execute
            or args.expected_source_sha256
            or args.batch_size != 1000
        ):
            raise RuntimeError("Backup confirmation flags only apply to --migrate-database")
        from scripts.check_production_database import format_human_report, format_json_report

        report = inspect_configured_database()
        print(format_json_report(report) if args.json else format_human_report(report))
        overall = report["summary"]["overall"]
        return 2 if overall == "blocked" else 1 if overall == "warning" else 0

    if args.import_sqlite:
        if args.json or args.backup_file:
            raise RuntimeError(
                "--json and --backup-file do not apply to --import-sqlite"
            )
        from backend.config import Config
        from backend.migrate_to_mysql import run_migration

        run_migration(
            args.import_sqlite,
            Config.SQLALCHEMY_DATABASE_URI,
            execute=args.execute,
            yes=args.yes,
            batch_size=args.batch_size,
            expected_source_sha256=args.expected_source_sha256 or None,
        )
        return 0

    if args.json or args.execute or args.expected_source_sha256 or args.batch_size != 1000:
        raise RuntimeError("SQLite import flags only apply to --import-sqlite")
    migrate_configured_database(
        backup_file=args.backup_file,
        confirmed=args.yes,
    )
    print("Database migration and post-migration preflight passed.")
    return 0
