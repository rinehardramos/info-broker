"""Docker tool node — base class for pipeline nodes that run binaries inside Docker containers."""

from __future__ import annotations
import asyncio
import json
import logging
import shlex
from typing import Any

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class DockerToolNode:
    """Base class for pipeline nodes that execute tools inside Docker containers.

    Subclasses must set:
      - node_type: str
      - display_name: str
      - docker_image: str (e.g., "info-broker/exiftool:latest")
      - docker_command_template: str (e.g., "exiftool -json {input_file}")
      - output_format: str ("json" | "text" | "lines")

    Optionally override:
      - config_schema: dict
      - category: str (default "enrich")
      - timeout_seconds: int (default 60)
      - network_enabled: bool (default False — runs with --network=none)
      - memory_limit: str (default "512m")
    """

    node_type: str = ""
    display_name: str = ""
    category: str = "enrich"
    docker_image: str = ""
    docker_command_template: str = ""
    output_format: str = "json"
    timeout_seconds: int = 60
    network_enabled: bool = False
    memory_limit: str = "512m"

    config_schema: dict = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "title": "Input",
                "description": "Input data or file path for the tool",
            },
        },
        "required": [],
    }

    _REASON: str = "Docker-sandboxed tool execution"

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        """Run the Docker container and parse output."""
        args = self._build_args(config, inputs)
        if not args and not config.get("input"):
            return [{"error": "No input provided", "source": self.node_type, "reason": self._REASON}]

        if not _docker_available():
            return [{"error": "Docker not available", "source": self.node_type, "reason": self._REASON}]

        if not await _image_exists(self.docker_image):
            return [
                {
                    "error": f"Docker image {self.docker_image} not found. Build it first.",
                    "source": self.node_type,
                    "reason": self._REASON,
                }
            ]

        try:
            stdout = await self._run_container(args, config.get("stdin_data"))
            results = self._parse_output(stdout)
            return [{"source": self.node_type, "reason": self._REASON, **r} for r in results]
        except asyncio.TimeoutError:
            return [
                {
                    "error": f"Container timed out after {self.timeout_seconds}s",
                    "source": self.node_type,
                    "reason": self._REASON,
                }
            ]
        except Exception as exc:
            log.warning("%s: container error: %s", self.node_type, exc)
            return [{"error": str(exc), "source": self.node_type, "reason": self._REASON}]

    def _build_args(self, config: dict, inputs: list[dict]) -> str:
        """Build the command string from config and inputs."""
        input_val = config.get("input", "")
        if not input_val:
            for item in inputs:
                input_val = (
                    item.get("input")
                    or item.get("target")
                    or item.get("query")
                    or ""
                )
                if input_val:
                    break

        if self.docker_command_template:
            _reserved = {"input", "input_file", "target"}
            extra = {k: v for k, v in config.items() if isinstance(v, str) and k not in _reserved}
            return self.docker_command_template.format(
                input=input_val,
                input_file=input_val,
                target=input_val,
                **extra,
            )
        return input_val

    async def _run_container(self, command_args: str, stdin_data: str | None = None) -> str:
        """Run the Docker container and return stdout."""
        docker_cmd = [
            "docker", "run", "--rm",
            f"--memory={self.memory_limit}",
            "--cpus=1",
            "--read-only",
        ]

        if not self.network_enabled:
            docker_cmd.append("--network=none")

        docker_cmd.append(self.docker_image)

        if command_args:
            docker_cmd.extend(shlex.split(command_args))

        log.debug("%s: running %s", self.node_type, " ".join(docker_cmd))

        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(stdin_data.encode() if stdin_data else None),
            timeout=self.timeout_seconds,
        )

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Container exited with code {proc.returncode}: {stderr[:500]}"
            )

        return stdout

    def _parse_output(self, stdout: str) -> list[dict]:
        """Parse container stdout into result dicts."""
        if not stdout:
            return [{"output": "", "note": "No output from container"}]

        if self.output_format == "json":
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    return data
                return [data]
            except json.JSONDecodeError:
                return [{"raw_output": stdout, "parse_error": "Invalid JSON"}]

        elif self.output_format == "lines":
            lines = [line.strip() for line in stdout.split("\n") if line.strip()]
            return [{"line": line} for line in lines]

        else:  # text
            return [{"output": stdout}]


def _docker_available() -> bool:
    """Check if Docker CLI is available."""
    import shutil
    return shutil.which("docker") is not None


async def _image_exists(image: str) -> bool:
    """Check if a Docker image exists locally."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "image", "inspect", image,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except Exception:
        return False
