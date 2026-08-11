"""
Docker sandbox wrapper.

Runs arbitrary Python + pytest inside an isolated container with:
  - --network none        (no outbound internet)
  - --memory 256m         (OOM-kill runaway allocations)
  - --cpu-quota 50000     (50 % of one core)
  - Hard 30-second timeout enforced by container.wait(timeout=…)

Pathological code (infinite loops, fork bombs, large mallocs) is guaranteed
to terminate: the container is force-killed and a structured failure is returned.
The pipeline never hangs.
"""
from __future__ import annotations

import io
import os
import tarfile

import docker

IMAGE_TAG = "autocritic-sandbox:latest"
MEMORY_LIMIT = "256m"
CPU_QUOTA = 50_000     # 50 % of one CPU (100 000 = 100 %)
TIMEOUT_SEC = 30


def _build_image(client: docker.DockerClient) -> None:
    dockerfile_dir = os.path.dirname(os.path.abspath(__file__))
    client.images.build(path=dockerfile_dir, tag=IMAGE_TAG, rm=True, quiet=True)


def _pack_tar(files: dict[str, str]) -> bytes:
    """Return an in-memory tar archive containing {filename: utf-8 content}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in files.items():
            encoded = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(encoded)
            tar.addfile(info, io.BytesIO(encoded))
    return buf.getvalue()


def run_in_sandbox(files: dict[str, str]) -> dict:
    """
    Write *files* into a fresh container and run pytest.

    Args:
        files: {relative_filename: file_content}

    Returns:
        {"stdout": str, "stderr": str, "exit_code": int}

    The function NEVER raises — all failure modes return exit_code != 0.
    """
    client = docker.from_env()
    _build_image(client)

    container = client.containers.create(
        image=IMAGE_TAG,
        command=["pytest", "--tb=short", "-v", "--no-header"],
        network_mode="none",
        mem_limit=MEMORY_LIMIT,
        cpu_quota=CPU_QUOTA,
        detach=True,
    )

    try:
        container.put_archive("/code", _pack_tar(files))
        container.start()

        try:
            result = container.wait(timeout=TIMEOUT_SEC)
            exit_code = result.get("StatusCode", 1)
        except Exception:
            # Timeout — force-kill, never hang
            try:
                container.kill()
            except Exception:
                pass
            return {
                "stdout": "",
                "stderr": f"[autocritic] Container killed: exceeded {TIMEOUT_SEC}s timeout.",
                "exit_code": 124,
            }

        logs = container.logs(stdout=True, stderr=True).decode(errors="replace")
        return {"stdout": logs, "stderr": "", "exit_code": exit_code}

    except Exception as exc:
        return {"stdout": "", "stderr": f"[autocritic] Sandbox error: {exc}", "exit_code": 1}

    finally:
        try:
            container.remove(force=True)
        except Exception:
            pass
