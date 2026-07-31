"""Guarded foreign-key orphan repair for the project SQLite database.

The command is a dry-run by default: it only reports orphaned foreign-key
references and the placeholder parent rows it would insert. A destructive
repair requires both ``--execute`` and ``--yes``, creates an online backup
under ``data/backups/`` first, writes an audit log to ``logs/db_repair.log``,
and re-checks that no orphan remains before committing (otherwise it rolls
back). This replaces ad-hoc root-level repair scripts; data repair must only
happen through this entry or the guarded ``backend/migrate_to_mysql.py``
preflight.

Example:

    python scripts/repair_sqlite_fk_orphans.py --sqlite-path data/app.db
    python scripts/repair_sqlite_fk_orphans.py --sqlite-path data/app.db \
        --execute --yes
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = ROOT / "data" / "app.db"
BACKUP_DIR = ROOT / "data" / "backups"
LOG_PATH = ROOT / "logs" / "db_repair.log"
PLACEHOLDER_TEXT = "[FK修复占位]"


@dataclass(frozen=True)
class ForeignKeyRef:
    child_table: str
    parent_table: str
    child_columns: tuple
    parent_columns: tuple

    @property
    def label(self):
        return (
            f"{self.child_table}.{'/'.join(self.child_columns)} -> "
            f"{self.parent_table}.{'/'.join(self.parent_columns)}"
        )


def _build_logger(execute):
    logger = logging.getLogger("repair_sqlite_fk_orphans")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stream)
    if execute:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        audit = logging.FileHandler(LOG_PATH, encoding="utf-8")
        audit.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(audit)
    return logger


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _connect_read_only(path):
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _user_tables(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master"
        " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        " ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def _foreign_keys(connection):
    refs = []
    for table in _user_tables(connection):
        grouped = {}
        for row in connection.execute(f"PRAGMA foreign_key_list({_quote(table)})"):
            fk_id, _seq, parent, child_col, parent_col = row[0], row[1], row[2], row[3], row[4]
            grouped.setdefault(fk_id, {"parent": parent, "pairs": []})
            grouped[fk_id]["pairs"].append((child_col, parent_col or "rowid"))
        for entry in grouped.values():
            child_cols = tuple(pair[0] for pair in entry["pairs"])
            parent_cols = tuple(pair[1] for pair in entry["pairs"])
            refs.append(ForeignKeyRef(table, entry["parent"], child_cols, parent_cols))
    return refs


def _orphan_key_tuples(connection, ref):
    child = _quote(ref.child_table)
    parent = _quote(ref.parent_table)
    select_cols = ", ".join(f"c.{_quote(col)}" for col in ref.child_columns)
    not_null = " AND ".join(f"c.{_quote(col)} IS NOT NULL" for col in ref.child_columns)
    join_cond = " AND ".join(
        f"p.{_quote(pcol)} = c.{_quote(ccol)}"
        for ccol, pcol in zip(ref.child_columns, ref.parent_columns)
    )
    sql = (
        f"SELECT DISTINCT {select_cols} FROM {child} AS c"
        f" WHERE {not_null}"
        f" AND NOT EXISTS (SELECT 1 FROM {parent} AS p WHERE {join_cond})"
    )
    return [tuple(row) for row in connection.execute(sql).fetchall()]


def _placeholder_for_column(column_type):
    affinity = (column_type or "").upper()
    if "INT" in affinity:
        return 0
    if any(token in affinity for token in ("REAL", "FLOA", "DOUB", "NUMERIC", "DECIMAL")):
        return 0
    if "BLOB" in affinity:
        return b""
    return PLACEHOLDER_TEXT


def _planned_insert(connection, ref, key_tuple):
    """Build one placeholder parent INSERT covering NOT NULL columns."""
    columns = {}
    for row in connection.execute(f"PRAGMA table_info({_quote(ref.parent_table)})"):
        _cid, name, col_type, not_null, default, _pk = row
        columns[name] = (col_type, bool(not_null), default)

    values = dict(zip(ref.parent_columns, key_tuple))
    for name, (col_type, not_null, default) in columns.items():
        if name in values or not not_null or default is not None:
            continue
        values[name] = _placeholder_for_column(col_type)

    names = list(values)
    sql = (
        f"INSERT INTO {_quote(ref.parent_table)}"
        f" ({', '.join(_quote(name) for name in names)})"
        f" VALUES ({', '.join('?' for _ in names)})"
    )
    return sql, tuple(values[name] for name in names)


def _collect_plan(connection):
    plan = []
    for ref in _foreign_keys(connection):
        orphans = _orphan_key_tuples(connection, ref)
        for key_tuple in orphans:
            sql, params = _planned_insert(connection, ref, key_tuple)
            plan.append((ref, key_tuple, sql, params))
    return plan


def _backup_database(source_path, logger):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"pre-fk-repair-{stamp}-{source_path.stem}.db"
    with closing(sqlite3.connect(source_path)) as source, closing(
        sqlite3.connect(backup_path)
    ) as target:
        source.backup(target)
    logger.info("已创建执行前备份: %s", backup_path)
    return backup_path


def _execute_plan(path, plan, logger):
    backup_path = _backup_database(path, logger)
    connection = sqlite3.connect(path)
    try:
        connection.execute("BEGIN")
        for ref, key_tuple, sql, params in plan:
            connection.execute(sql, params)
            logger.info(
                "已插入占位父记录 %s: %s = %s",
                ref.parent_table,
                "/".join(ref.parent_columns),
                key_tuple,
            )
        remaining = [
            (ref.label, count)
            for ref in _foreign_keys(connection)
            if (count := len(_orphan_key_tuples(connection, ref)))
        ]
        if remaining:
            connection.rollback()
            for label, count in remaining:
                logger.error("修复后仍有孤儿引用 %s: %d 条，已回滚", label, count)
            raise RuntimeError("post-repair verification failed; transaction rolled back")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    logger.info("修复完成并通过复检；备份保留于 %s", backup_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help=f"SQLite database path (default: {DEFAULT_SQLITE_PATH})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="apply the repair; without this flag the command is a dry-run",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm the destructive repair together with --execute",
    )
    args = parser.parse_args(argv)

    path = args.sqlite_path if args.sqlite_path.is_absolute() else ROOT / args.sqlite_path
    if not path.is_file():
        print(f"error: SQLite database not found: {path}", file=sys.stderr)
        return 2
    if args.execute and not args.yes:
        print("error: --execute requires --yes to confirm", file=sys.stderr)
        return 2

    logger = _build_logger(args.execute)
    logger.info("目标数据库: %s", path)

    with closing(_connect_read_only(path)) as scan:
        plan = _collect_plan(scan)

    if not plan:
        logger.info("未发现孤儿外键引用，无需修复。")
        return 0

    logger.info("发现 %d 条缺失的父记录：", len(plan))
    for ref, key_tuple, sql, params in plan:
        logger.info("  %s 缺失父键 %s", ref.label, key_tuple)
        logger.info("    计划执行: %s -- 参数 %s", sql, params)

    if not args.execute:
        logger.info("dry-run 结束，未写入任何数据。使用 --execute --yes 应用修复。")
        return 0

    logger.info("开始执行修复（审计日志: %s）", LOG_PATH)
    _execute_plan(path, plan, logger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
