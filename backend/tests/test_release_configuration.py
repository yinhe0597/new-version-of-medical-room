import re
from pathlib import Path
import unittest

from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"


def _requirement_names(path):
    names = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


class ReleaseConfigurationTestCase(unittest.TestCase):
    def test_release_version_sources_are_consistent(self):
        version = (PROJECT_ROOT / "VERSION").read_text(encoding="ascii").strip()
        self.assertRegex(version, r"^[0-9]+\.[0-9]+\.[0-9]+$")

        linux_build = (PROJECT_ROOT / "build_linux.sh").read_text(encoding="utf-8")
        github_workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "build-linux-release.yml"
        ).read_text(encoding="utf-8")
        windows_version = (PROJECT_ROOT / "version_info.txt").read_text(
            encoding="utf-8"
        )
        production_entry = (PROJECT_ROOT / "run_prod.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('VERSION_FILE="$SCRIPT_DIR/VERSION"', linux_build)
        self.assertIsNone(
            re.search(r'^VERSION="[0-9]', linux_build, flags=re.MULTILINE),
            linux_build,
        )
        self.assertIn("< VERSION", github_workflow)
        self.assertIn("does not match VERSION", github_workflow)
        self.assertIn(f"filevers=({version.replace('.', ', ')}, 0)", windows_version)
        self.assertIn(f"open{version}", windows_version)
        self.assertIn(f"open{version}", production_entry)
        self.assertNotIn("glibc 2.17+", github_workflow)

    def test_linux_release_uses_the_discovered_alembic_head(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "build-linux-release.yml"
        ).read_text(encoding="utf-8")

        config = Config(str(BACKEND_DIR / "migrations" / "alembic.ini"))
        config.set_main_option(
            "script_location", str(BACKEND_DIR / "migrations")
        )
        heads = ScriptDirectory.from_config(config).get_heads()
        self.assertEqual(len(heads), 1)

        self.assertIn(
            "from scripts.validate_mysql_alembic import CURRENT_HEAD", workflow
        )
        self.assertIn("if heads != [CURRENT_HEAD]", workflow)
        self.assertNotRegex(workflow, r"Expected one Alembic head [0-9a-f]{12}")

    def test_linux_release_checks_every_packaged_migration(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "build-linux-release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('Path("backend/migrations/versions").glob("*.py")', workflow)
        self.assertIn("*migration_files", workflow)

    def test_gitee_pipelines_run_current_project_gates(self):
        workflow_dir = PROJECT_ROOT / ".workflow"
        for name in (
            "branch-pipeline.yml",
            "master-pipeline.yml",
            "pr-pipeline.yml",
        ):
            with self.subTest(name=name):
                content = (workflow_dir / name).read_text(encoding="utf-8")
                self.assertIn("backend/requirements-ci.txt", content)
                self.assertIn("python3 run_backend_tests.py", content)
                self.assertIn("python3 -m pip_audit", content)
                self.assertIn("npm ci", content)
                self.assertIn("npm run audit:production", content)
                self.assertIn("npm run build", content)
                self.assertNotIn("pip3 install -r requirements.txt", content)
                self.assertNotIn("python3 ./main.py", content)

        main_workflow = (workflow_dir / "master-pipeline.yml").read_text(
            encoding="utf-8"
        )
        pr_workflow = (workflow_dir / "pr-pipeline.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("name: main-pipeline", main_workflow)
        self.assertIn("- main", main_workflow)
        self.assertIn("- main", pr_workflow)

    def test_release_constraints_cover_all_direct_dependencies(self):
        runtime_names = _requirement_names(BACKEND_DIR / "requirements.txt")
        build_names = _requirement_names(BACKEND_DIR / "requirements-build.txt")
        ci_names = _requirement_names(BACKEND_DIR / "requirements-ci.txt")
        constraint_path = BACKEND_DIR / "constraints.txt"
        constraints = constraint_path.read_text(encoding="utf-8")
        constrained_names = _requirement_names(constraint_path)

        self.assertIn("-c constraints.txt", (
            BACKEND_DIR / "requirements-build.txt"
        ).read_text(encoding="utf-8"))
        self.assertEqual(
            set(),
            (runtime_names | build_names | ci_names) - constrained_names,
        )
        for raw_line in constraints.splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[^=\s]+$")


if __name__ == "__main__":
    unittest.main()
