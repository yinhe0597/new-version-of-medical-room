import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = REPOSITORY_ROOT / "run.sh"


FAKE_EXECUTABLE = r"""#!/bin/bash
set -u

fake_app_dir="$(cd "$(dirname "$0")" && pwd)"
printf '%s\n' "$$" >> "$MEDICAL_ROOM_TEST_LAUNCH_FILE"
"$MEDICAL_ROOM_TEST_PYTHON" "$fake_app_dir/fake_ready_server.py" &
server_pid=$!
printf '%s\n' "$server_pid" >> "$MEDICAL_ROOM_TEST_SERVER_PID_FILE"

cleanup() {
    trap - EXIT HUP INT TERM
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
    exit 0
}

trap cleanup EXIT HUP INT TERM
wait "$server_pid"
"""


FAKE_CURL = r"""#!/bin/bash
"$MEDICAL_ROOM_TEST_REAL_CURL" "$@"
result=$?
if [ "$result" -eq 28 ]; then
    exit 7
fi
exit "$result"
"""


TEST_BASH_ENV = r"""test_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATH="$test_root/bin:$PATH"
export PATH
if [ "${MEDICAL_ROOM_TEST_HIDE_FLOCK:-0}" = "1" ]; then
    command() {
        if [ "$#" -eq 2 ] && [ "$1" = "-v" ] && [ "$2" = "flock" ]; then
            return 1
        fi
        builtin command "$@"
    }
fi
unset test_root
"""


FAKE_READY_SERVER = r"""import http.server
import os
import time
from pathlib import Path


started_at = time.monotonic()
status_file = Path(os.environ["MEDICAL_ROOM_TEST_STATUS_FILE"])
ready_delay = float(os.environ.get("MEDICAL_ROOM_TEST_READY_DELAY", "0"))


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            status = int(status_file.read_text(encoding="ascii").strip())
        except FileNotFoundError:
            status = 200 if time.monotonic() - started_at >= ready_delay else 503
        except (OSError, ValueError):
            status = 503
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        return


server = http.server.ThreadingHTTPServer(
    ("127.0.0.1", int(os.environ["MEDICAL_ROOM_TEST_PORT"])), Handler
)
server.serve_forever()
"""


class _FixedStatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(self.server.response_status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        return


class RunShProcessManagementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name == "nt":
            raise unittest.SkipTest(
                "run.sh process identity tests require native Linux /proc semantics"
            )
        cls.bash = cls._find_bash()
        if cls.bash is None:
            raise unittest.SkipTest("bash is required for run.sh process tests")
        proc_check = subprocess.run(
            [cls.bash, "-c", "test -r /proc/$$/stat && test -r /proc/$$/environ"],
            capture_output=True,
            timeout=5,
        )
        if proc_check.returncode != 0:
            raise unittest.SkipTest("readable Linux/MSYS /proc process metadata is required")
        curl = subprocess.run(
            [cls.bash, "-c", "command -v curl"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        if curl.returncode != 0:
            raise unittest.SkipTest("curl is required for isolated readiness tests")
        cls.real_curl = curl.stdout.strip()

    @staticmethod
    def _find_bash():
        configured = os.environ.get("BASH")
        candidates = [configured]
        if os.name == "nt":
            candidates.append(r"C:\Program Files\Git\bin\bash.exe")
        candidates.append(shutil.which("bash"))
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(candidate)
        return None

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app_dir = Path(self.temp_dir.name)
        shutil.copy2(RUN_SCRIPT, self.app_dir / "run.sh")
        (self.app_dir / "medical_room").write_bytes(FAKE_EXECUTABLE.encode("ascii"))
        (self.app_dir / "fake_ready_server.py").write_bytes(
            FAKE_READY_SERVER.encode("ascii")
        )
        fake_bin = self.app_dir / "bin"
        fake_bin.mkdir()
        fake_curl = fake_bin / "curl"
        fake_curl.write_bytes(FAKE_CURL.encode("ascii"))
        fake_curl.chmod(0o755)
        (self.app_dir / "test-bash-env").write_bytes(TEST_BASH_ENV.encode("ascii"))
        self.port = self._unused_port()
        self.env = os.environ.copy()
        self.env.update(
            {
                "APP_ROOT": "./runtime",
                "BASH_ENV": "./test-bash-env",
                "MEDICAL_ROOM_READY_URL": f"http://127.0.0.1:{self.port}/ready",
                "MEDICAL_ROOM_STARTUP_TIMEOUT": "8",
                "MEDICAL_ROOM_LOCK_TIMEOUT": "8",
                "MEDICAL_ROOM_TEST_LAUNCH_FILE": "./launches",
                "MEDICAL_ROOM_TEST_PORT": str(self.port),
                "MEDICAL_ROOM_TEST_PYTHON": Path(sys.executable).as_posix(),
                "MEDICAL_ROOM_TEST_REAL_CURL": self.real_curl,
                "MEDICAL_ROOM_TEST_SERVER_PID_FILE": "./server-pids",
                "MEDICAL_ROOM_TEST_STATUS_FILE": "./ready-status",
                "PATH": str(fake_bin) + os.pathsep + self.env.get("PATH", ""),
            }
        )
        self.valid_pid_record = None

    def tearDown(self):
        try:
            if self.valid_pid_record is not None:
                self.pid_file.parent.mkdir(parents=True, exist_ok=True)
                self.pid_file.write_bytes(self.valid_pid_record)
            if self.pid_file.exists():
                self._run_script("stop", timeout=15)
        finally:
            self._terminate_test_processes()
            self.temp_dir.cleanup()

    @property
    def pid_file(self):
        return self.app_dir / "runtime" / ".medical_room.pid"

    @property
    def launch_file(self):
        return self.app_dir / "launches"

    @staticmethod
    def _unused_port():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def _run_script(self, command, *, timeout=20, env=None):
        return subprocess.run(
            [self.bash, "run.sh", command],
            cwd=self.app_dir,
            env=env or self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def _start_managed_service(self, *, ready_delay="0"):
        env = self.env.copy()
        env["MEDICAL_ROOM_TEST_READY_DELAY"] = ready_delay
        result = self._run_script("start", env=env)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.valid_pid_record = self.pid_file.read_bytes()
        return result

    def _start_controller(self, *, ready_delay="30"):
        env = self.env.copy()
        env["MEDICAL_ROOM_TEST_READY_DELAY"] = ready_delay
        env["MEDICAL_ROOM_STARTUP_TIMEOUT"] = "30"
        controller = subprocess.Popen(
            [self.bash, "run.sh", "start"],
            cwd=self.app_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.pid_file.exists():
                self.valid_pid_record = self.pid_file.read_bytes()
                return controller, env
            if controller.poll() is not None:
                stdout, stderr = controller.communicate(timeout=2)
                self.fail(
                    "start controller exited before writing its PID record: "
                    + stdout
                    + stderr
                )
            time.sleep(0.05)
        controller.kill()
        stdout, stderr = controller.communicate(timeout=5)
        self.fail("start controller did not write its PID record: " + stdout + stderr)

    def _launch_count(self):
        if not self.launch_file.exists():
            return 0
        return len(self.launch_file.read_text(encoding="ascii").splitlines())

    def _pid_is_alive(self, pid):
        result = subprocess.run(
            [self.bash, "-c", f"kill -0 {pid} 2>/dev/null"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0

    def _terminate_test_processes(self):
        pids = []
        for name in ("launches", "server-pids"):
            path = self.app_dir / name
            if not path.exists():
                continue
            for value in path.read_text(encoding="ascii").splitlines():
                if value.isdigit():
                    pids.append(value)
        if not pids:
            return
        subprocess.run(
            [
                self.bash,
                "-c",
                'shift; for pid in "$@"; do kill "$pid" 2>/dev/null || true; done',
                "cleanup",
                *pids,
            ],
            capture_output=True,
            timeout=5,
        )

    def test_start_refuses_existing_http_503_without_launching(self):
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.port), _FixedStatusHandler
        )
        server.response_status = 503
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = self._run_script("start")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(0, self._launch_count())
        self.assertFalse(self.pid_file.exists())

    def test_existing_managed_process_reports_current_readiness(self):
        self._start_managed_service()
        (self.app_dir / "ready-status").write_text("503\n", encoding="ascii")

        status = self._run_script("status")
        repeated_start = self._run_script("start")

        self.assertEqual(1, status.returncode, status.stdout + status.stderr)
        self.assertEqual(1, repeated_start.returncode, repeated_start.stdout + repeated_start.stderr)
        self.assertIn("readiness", status.stdout + status.stderr)
        self.assertEqual(1, self._launch_count())

    def test_stop_refuses_tampered_pid_identity(self):
        self._start_managed_service()
        original = self.valid_pid_record.decode("ascii").strip()
        pid, start_ticks, token = original.split("|")
        self.pid_file.write_text(
            f"{pid}|{start_ticks}|tampered-{token}\n", encoding="ascii"
        )

        result = self._run_script("stop")

        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self._pid_is_alive(pid))

    def test_concurrent_starts_launch_only_one_process(self):
        env = self.env.copy()
        env["MEDICAL_ROOM_TEST_READY_DELAY"] = "1"
        commands = [self.bash, "run.sh", "start"]
        first = subprocess.Popen(
            commands,
            cwd=self.app_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        second = subprocess.Popen(
            commands,
            cwd=self.app_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        first_output = first.communicate(timeout=20)
        second_output = second.communicate(timeout=20)
        combined_output = "".join(first_output + second_output)

        self.assertEqual(0, first.returncode, combined_output)
        self.assertEqual(0, second.returncode, combined_output)
        self.assertEqual(1, self._launch_count())
        self.valid_pid_record = self.pid_file.read_bytes()

    def test_missing_flock_fails_closed_without_launching(self):
        env = self.env.copy()
        env["MEDICAL_ROOM_TEST_HIDE_FLOCK"] = "1"

        result = self._run_script("start", env=env)

        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("flock", result.stdout + result.stderr)
        self.assertEqual(0, self._launch_count())
        self.assertFalse(self.pid_file.exists())

    def test_term_during_start_releases_lock_and_returns_failure(self):
        controller, env = self._start_controller()

        controller.terminate()
        stdout, stderr = controller.communicate(timeout=5)

        self.assertEqual(143, controller.returncode, stdout + stderr)
        status_env = env.copy()
        status_env["MEDICAL_ROOM_LOCK_TIMEOUT"] = "2"
        status = self._run_script("status", env=status_env, timeout=6)
        self.assertEqual(1, status.returncode, status.stdout + status.stderr)
        self.assertIn("readiness", status.stdout + status.stderr)

    def test_service_does_not_inherit_lock_after_controller_is_killed(self):
        controller, env = self._start_controller()

        controller.kill()
        stdout, stderr = controller.communicate(timeout=5)

        self.assertNotEqual(0, controller.returncode, stdout + stderr)
        status_env = env.copy()
        status_env["MEDICAL_ROOM_LOCK_TIMEOUT"] = "2"
        status = self._run_script("status", env=status_env, timeout=6)
        self.assertEqual(1, status.returncode, status.stdout + status.stderr)
        self.assertIn("readiness", status.stdout + status.stderr)


if __name__ == "__main__":
    unittest.main()
