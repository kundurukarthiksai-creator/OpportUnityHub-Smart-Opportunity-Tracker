import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request_json(url: str, method: str = "GET", body: dict | None = None, token: str | None = None) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def request_text(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def request_status(url: str) -> int:
    success = False
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def wait_for_health(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 35
    last_error = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Server exited before becoming healthy.")
        try:
            health = request_json(f"{base_url}/api/health")
            if health.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - surface final startup error below
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Server did not become healthy in time. Last error: {last_error}")


def main() -> int:
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_for_health(base_url, proc)

        health = request_json(f"{base_url}/api/health")
        assert health["status"] == "ok", health

        status, index_html = request_text(f"{base_url}/index.html")
        assert status == 200, status
        assert "OpportUnity" in index_html, "Frontend landing page did not render expected text."

        protected_status = request_status(f"{base_url}/api/opportunities")
        assert protected_status == 401, f"Expected protected route to return 401, got {protected_status}."

        email = f"smoke-{uuid4().hex[:10]}@example.com"
        registered = request_json(
            f"{base_url}/api/auth/register",
            method="POST",
            body={
                "email": email,
                "password": "SmokeTestPassword123!",
                "name": "Smoke Test User",
                "university": "ASU",
                "branch": "Computer Science",
                "year": "Graduate",
            },
        )
        token = registered.get("token")
        assert token, "Registration did not return a token."

        me = request_json(f"{base_url}/api/auth/me", token=token)
        assert me.get("email") == email, me

        stats = request_json(f"{base_url}/api/opportunities/stats", token=token)
        assert "total" in stats and "saved" in stats and "applied" in stats, stats

        print("Smoke test passed: health, static frontend, auth, and stats routes are working.")
        success = True
        return 0
    finally:
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=8)
        if not success:
            print("\n--- server output ---")
            print(output[-4000:])


if __name__ == "__main__":
    raise SystemExit(main())
