import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects import mysql, sqlite

from backend.app.models import Drug
from backend.app.utils.query import nulls_last_asc
from backend.runtime_secrets import SECRET_NAMES, ensure_runtime_secrets


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RuntimeSecretsTestCase(unittest.TestCase):
    def test_generated_secrets_are_stable_across_repeated_loads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = ensure_runtime_secrets(temp_dir, {})
            second = ensure_runtime_secrets(temp_dir, {})

            self.assertEqual(first, second)
            for name in SECRET_NAMES:
                self.assertGreaterEqual(len(first[name]), 32)

            with open(
                os.path.join(temp_dir, ".runtime-secrets.json"),
                "r",
                encoding="utf-8",
            ) as handle:
                self.assertEqual(json.load(handle), first)

    def test_concurrent_loads_share_one_secret_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(
                    executor.map(
                        lambda _: ensure_runtime_secrets(temp_dir, {}),
                        range(8),
                    )
                )

            self.assertTrue(all(result == results[0] for result in results))

    def test_concurrent_processes_share_one_secret_pair(self):
        script = (
            "import json; "
            "from backend.config import Config; "
            "print(json.dumps({"
            "'SECRET_KEY': Config.SECRET_KEY, "
            "'JWT_SECRET_KEY': Config.JWT_SECRET_KEY"
            "}, sort_keys=True))"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            child_env = os.environ.copy()
            for name in SECRET_NAMES:
                child_env.pop(name, None)
            child_env["APP_ROOT"] = temp_dir
            child_env["PYTHON_DOTENV_DISABLED"] = "1"
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", script],
                    cwd=PROJECT_ROOT,
                    env=child_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(4)
            ]
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr)
                results.append(json.loads(stdout))

            self.assertTrue(all(result == results[0] for result in results))

    def test_explicit_placeholder_secret_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                ensure_runtime_secrets(
                    temp_dir,
                    {
                        "SECRET_KEY": "replace-with-at-least-32-random-characters",
                        "JWT_SECRET_KEY": "valid-jwt-secret-value-with-at-least-32-characters",
                    },
                )


class PortableOrderingTestCase(unittest.TestCase):
    def test_nulls_last_ordering_compiles_for_mysql_and_sqlite(self):
        statement = select(Drug.id).order_by(
            *nulls_last_asc(Drug.storage_location),
            Drug.id.desc(),
        )

        for dialect in (mysql.dialect(), sqlite.dialect()):
            sql = str(statement.compile(dialect=dialect)).upper()
            self.assertNotIn("NULLS LAST", sql)
            self.assertIn("CASE WHEN", sql)
            self.assertIn("IS NULL", sql)


if __name__ == "__main__":
    unittest.main()
