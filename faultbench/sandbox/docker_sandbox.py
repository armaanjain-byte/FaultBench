"""Docker sandbox lifecycle management for FaultBench.

Manages the complete lifecycle of isolated Docker containers used to
run coding agents against benchmark tasks:

1. Build/pull the sandbox image
2. Create a container with resource constraints
3. Copy task files into the container
4. Start the container
5. Monitor execution with timeout
6. Extract logs and artifacts
7. Stop and remove the container

All Docker operations use the Docker SDK for Python.
"""

from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path
from typing import Optional

import docker
import docker.errors
from docker.models.containers import Container

from faultbench.logging import get_logger
from faultbench.models import SandboxConfig

log = get_logger(__name__)


class DockerSandboxError(Exception):
    """Raised when a Docker sandbox operation fails."""


class DockerSandbox:
    """Manages an isolated Docker container for benchmark execution.

    Usage::

        sandbox = DockerSandbox(config)
        sandbox.create(task_work_dir)
        sandbox.start()
        exit_code = sandbox.wait(timeout=900)
        logs = sandbox.get_logs()
        sandbox.cleanup()

    Or as a context manager::

        with DockerSandbox(config) as sandbox:
            sandbox.create(task_work_dir)
            sandbox.start()
            exit_code = sandbox.wait()
    """

    def __init__(self, config: SandboxConfig) -> None:
        self._config = config
        self._client: Optional[docker.DockerClient] = None
        self._container: Optional[Container] = None
        self._container_id: Optional[str] = None

    @property
    def client(self) -> docker.DockerClient:
        """Lazy-initialized Docker client."""
        if self._client is None:
            try:
                self._client = docker.from_env()
                self._client.ping()
                log.info("docker_client_connected")
            except docker.errors.DockerException as exc:
                raise DockerSandboxError(
                    "Failed to connect to Docker daemon. "
                    "Is Docker running? Error: " + str(exc)
                ) from exc
        return self._client

    @property
    def container(self) -> Container:
        """Return the active container, raising if not created."""
        if self._container is None:
            raise DockerSandboxError("Container has not been created yet")
        return self._container

    def ensure_image(self) -> None:
        """Ensure the sandbox image exists locally.

        Tries to find the image locally first.  If not found, attempts to
        pull it from the registry.

        Raises:
            DockerSandboxError: If the image cannot be found or pulled.
        """
        image_name = self._config.image
        log.info("docker_ensure_image", image=image_name)

        try:
            self.client.images.get(image_name)
            log.info("docker_image_found_locally", image=image_name)
            return
        except docker.errors.ImageNotFound:
            log.info("docker_image_not_found_locally", image=image_name)

        try:
            log.info("docker_image_pulling", image=image_name)
            self.client.images.pull(image_name)
            log.info("docker_image_pulled", image=image_name)
        except docker.errors.APIError as exc:
            raise DockerSandboxError(
                f"Failed to pull image '{image_name}': {exc}"
            ) from exc

    def create(
        self,
        task_work_dir: Path,
        *,
        environment: Optional[dict[str, str]] = None,
        command: Optional[str] = None,
    ) -> str:
        """Create a new container with the task files mounted.

        Args:
            task_work_dir: Path to the working copy of the task.
            environment: Environment variables to set in the container.
            command: Override the default container command.

        Returns:
            The container ID.

        Raises:
            DockerSandboxError: If container creation fails.
        """
        self.ensure_image()

        container_name = f"faultbench-{task_work_dir.name}-{int(time.time())}"
        log.info(
            "docker_container_creating",
            name=container_name,
            image=self._config.image,
            memory_limit=self._config.memory_limit,
            cpu_quota=self._config.cpu_quota,
        )

        try:
            self._container = self.client.containers.create(
                image=self._config.image,
                name=container_name,
                command=command or "sleep infinity",
                environment=environment or {},
                volumes={
                    str(task_work_dir.resolve()): {
                        "bind": "/workspace",
                        "mode": "rw",
                    }
                },
                working_dir="/workspace",
                mem_limit=self._config.memory_limit,
                cpu_quota=self._config.cpu_quota,
                detach=True,
                stdin_open=True,
                tty=False,
            )
            self._container_id = self._container.id
            log.info(
                "docker_container_created",
                container_id=self._container_id[:12],
                name=container_name,
            )
            return self._container_id
        except docker.errors.APIError as exc:
            raise DockerSandboxError(
                f"Failed to create container: {exc}"
            ) from exc

    def start(self) -> None:
        """Start the container.

        Raises:
            DockerSandboxError: If the container fails to start.
        """
        log.info("docker_container_starting", container_id=self._container_id[:12] if self._container_id else "N/A")
        try:
            self.container.start()
            log.info("docker_container_started", container_id=self._container_id[:12] if self._container_id else "N/A")
        except docker.errors.APIError as exc:
            raise DockerSandboxError(
                f"Failed to start container: {exc}"
            ) from exc

    def exec_command(
        self,
        command: str | list[str],
        *,
        timeout: Optional[int] = None,
        environment: Optional[dict[str, str]] = None,
    ) -> tuple[int, str]:
        """Execute a command inside the running container.

        Args:
            command: Shell command string or list of args.
            timeout: Optional timeout in seconds.
            environment: Additional environment variables.

        Returns:
            Tuple of (exit_code, output_text).

        Raises:
            DockerSandboxError: If execution fails.
        """
        if isinstance(command, str):
            cmd = ["sh", "-c", command]
        else:
            cmd = command

        log.info(
            "docker_exec_start",
            container_id=self._container_id[:12] if self._container_id else "N/A",
            command=command if isinstance(command, str) else " ".join(command),
        )

        try:
            exec_result = self.container.exec_run(
                cmd,
                environment=environment or {},
                demux=False,
            )
            exit_code = exec_result.exit_code
            output = exec_result.output.decode("utf-8", errors="replace") if exec_result.output else ""

            log.info(
                "docker_exec_complete",
                container_id=self._container_id[:12] if self._container_id else "N/A",
                exit_code=exit_code,
                output_length=len(output),
            )
            return exit_code, output
        except docker.errors.APIError as exc:
            raise DockerSandboxError(
                f"Command execution failed in container: {exc}"
            ) from exc

    def wait(self, *, timeout: Optional[int] = None) -> int:
        """Wait for the container to finish execution.

        Args:
            timeout: Maximum seconds to wait.  Defaults to the config's
                     ``max_runtime_seconds``.

        Returns:
            Container exit code.

        Raises:
            DockerSandboxError: If the container times out or errors.
        """
        effective_timeout = timeout or self._config.max_runtime_seconds
        log.info(
            "docker_container_waiting",
            container_id=self._container_id[:12] if self._container_id else "N/A",
            timeout_seconds=effective_timeout,
        )

        try:
            result = self.container.wait(timeout=effective_timeout)
            status_code = result.get("StatusCode", -1)
            log.info(
                "docker_container_finished",
                container_id=self._container_id[:12] if self._container_id else "N/A",
                exit_code=status_code,
            )
            return status_code
        except Exception as exc:
            # Timeout or connection error
            log.error(
                "docker_container_timeout",
                container_id=self._container_id[:12] if self._container_id else "N/A",
                timeout_seconds=effective_timeout,
                error=str(exc),
            )
            self._force_stop()
            raise DockerSandboxError(
                f"Container exceeded timeout of {effective_timeout}s"
            ) from exc

    def get_logs(self, *, tail: Optional[int] = None) -> str:
        """Retrieve container logs.

        Args:
            tail: Number of lines from the end.  ``None`` returns all.

        Returns:
            Combined stdout + stderr as a string.
        """
        try:
            kwargs: dict = {"stdout": True, "stderr": True}
            if tail is not None:
                kwargs["tail"] = tail
            raw_logs = self.container.logs(**kwargs)
            return raw_logs.decode("utf-8", errors="replace")
        except docker.errors.APIError as exc:
            log.error("docker_logs_failed", error=str(exc))
            return f"[ERROR: Could not retrieve logs: {exc}]"

    def copy_file_from_container(
        self, container_path: str, host_path: Path
    ) -> None:
        """Copy a file from the container to the host.

        Args:
            container_path: Path inside the container.
            host_path: Destination on the host filesystem.
        """
        try:
            bits, _ = self.container.get_archive(container_path)
            stream = io.BytesIO()
            for chunk in bits:
                stream.write(chunk)
            stream.seek(0)

            with tarfile.open(fileobj=stream, mode="r") as tar:
                host_path.parent.mkdir(parents=True, exist_ok=True)
                # Extract the single file
                for member in tar.getmembers():
                    member.name = host_path.name
                    tar.extract(member, path=str(host_path.parent))

            log.info(
                "docker_file_copied",
                container_path=container_path,
                host_path=str(host_path),
            )
        except docker.errors.APIError as exc:
            log.error(
                "docker_file_copy_failed",
                container_path=container_path,
                error=str(exc),
            )
            raise DockerSandboxError(
                f"Failed to copy {container_path} from container: {exc}"
            ) from exc

    def _force_stop(self) -> None:
        """Force-stop the container (used on timeout)."""
        try:
            self.container.stop(timeout=10)
            log.warning(
                "docker_container_force_stopped",
                container_id=self._container_id[:12] if self._container_id else "N/A",
            )
        except docker.errors.APIError:
            log.error("docker_container_stop_failed")

    def cleanup(self) -> None:
        """Stop and remove the container, cleaning up resources."""
        if self._container is None:
            return

        container_id = self._container_id[:12] if self._container_id else "N/A"
        log.info("docker_container_cleanup_start", container_id=container_id)

        try:
            self._container.stop(timeout=10)
        except docker.errors.APIError:
            pass  # May already be stopped

        try:
            self._container.remove(force=True)
            log.info("docker_container_removed", container_id=container_id)
        except docker.errors.APIError as exc:
            log.error("docker_container_remove_failed", container_id=container_id, error=str(exc))

        self._container = None
        self._container_id = None

    def __enter__(self) -> DockerSandbox:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.cleanup()
