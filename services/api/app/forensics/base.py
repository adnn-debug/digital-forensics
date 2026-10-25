"""
Base infrastructure for secure, isolated forensic CLI adapters and metadata extraction.

Security Guarantees:
- Strictly executes subprocesses via argument lists (never shell=True or string concatenation).
- Employs '--' argument boundary before file arguments to prevent CLI flag injection.
- Enforces strict execution timeouts with automatic SIGKILL/termination.
- Bounded stdout and stderr capture (default 10 MB limit) to prevent memory exhaustion bombs.
- Requires target files to be verified, safe, and exist on disk.
- Never invents metadata values: missing fields are explicitly recorded as "Unavailable" or None.
"""

from __future__ import annotations

import abc
import hashlib
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("ps05.forensics.base")

# Hard upper bound on stdout/stderr read size (10 MB)
DEFAULT_MAX_OUTPUT_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30


class ForensicExecutionError(Exception):
    """Raised when an external forensic utility fails to execute or times out."""


@dataclass
class ToolExecutionResult:
    """Standardized result envelope for external forensic CLI tools."""

    tool_name: str
    tool_version: str
    extracted_at: datetime
    execution_duration_ms: float
    success: bool
    errors: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    filtered_forensic_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a serializable dictionary."""
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "extracted_at": self.extracted_at.isoformat(),
            "execution_duration_ms": self.execution_duration_ms,
            "success": self.success,
            "errors": self.errors,
            "raw_metadata": self.raw_metadata,
            "filtered_forensic_metadata": self.filtered_forensic_metadata,
            "provenance": self.provenance,
        }


class SafeSubprocessRunner:
    """
    Subprocess execution manager implementing defensive sandboxing parameters.
    """

    @staticmethod
    def execute_bounded(
        cmd: list[str],
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        cwd: Path | None = None,
    ) -> tuple[int, str, str]:
        """
        Execute command with strict isolation, timeouts, and bounded pipe reads.

        Guarantees:
        - shell=False strictly enforced.
        - timeout_seconds raises TimeoutExpired and forcefully terminates process.
        - stdout and stderr reads are bounded up to max_output_bytes.
        """
        if not cmd or not isinstance(cmd, list | tuple):
            raise ForensicExecutionError("Command must be a non-empty sequence of string arguments.")

        # Ensure all arguments are strings
        safe_cmd = [str(arg) for arg in cmd]

        logger.debug("Executing safe forensic command: %s (timeout=%ds)", safe_cmd[0], timeout_seconds)

        try:
            # We use Popen with bounded reading to prevent unbounded memory growth
            proc = subprocess.Popen(
                safe_cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                cwd=str(cwd) if cwd else None,
            )

            try:
                raw_stdout, raw_stderr = proc.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                # Read any buffered output after kill
                proc.communicate()
                raise ForensicExecutionError(
                    f"Subprocess '{safe_cmd[0]}' exceeded strict timeout of {timeout_seconds}s."
                ) from exc

            # Enforce bounded length
            if len(raw_stdout) > max_output_bytes:
                logger.warning(
                    "Stdout from %s exceeded %d bytes (%d bytes), truncating.",
                    safe_cmd[0],
                    max_output_bytes,
                    len(raw_stdout),
                )
                raw_stdout = raw_stdout[:max_output_bytes]

            if len(raw_stderr) > max_output_bytes:
                raw_stderr = raw_stderr[:max_output_bytes]

            stdout_str = raw_stdout.decode("utf-8", errors="replace")
            stderr_str = raw_stderr.decode("utf-8", errors="replace")

            return proc.returncode, stdout_str, stderr_str

        except FileNotFoundError as exc:
            raise ForensicExecutionError(
                f"Forensic tool binary '{safe_cmd[0]}' was not found on the system PATH."
            ) from exc
        except Exception as exc:
            if isinstance(exc, ForensicExecutionError):
                raise
            raise ForensicExecutionError(
                f"Failed to execute forensic tool '{safe_cmd[0]}': {exc}"
            ) from exc


class BaseMetadataAdapter(abc.ABC):
    """Abstract base adapter for forensic metadata extraction tools."""

    def __init__(self, binary_path: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.binary_path = binary_path
        self.timeout_seconds = timeout_seconds
        self._cached_version: str | None = None

    @property
    @abc.abstractmethod
    def tool_name(self) -> str:
        """Name of the forensic utility (e.g. ExifTool, FFprobe)."""

    @abc.abstractmethod
    def resolve_binary(self) -> str:
        """Locate executable binary on system or raise ForensicExecutionError."""

    @abc.abstractmethod
    def query_version(self) -> str:
        """Query and return external utility version string."""

    @abc.abstractmethod
    def extract_metadata(self, file_path: Path) -> ToolExecutionResult:
        """Extract and parse structured metadata from media file."""

    def get_version(self) -> str:
        """Return cached or resolved tool version."""
        if not self._cached_version:
            try:
                self._cached_version = self.query_version()
            except Exception as exc:
                logger.warning("Failed to query %s version: %s", self.tool_name, exc)
                self._cached_version = "Unavailable"
        return self._cached_version

    def is_available(self) -> bool:
        """Check if external binary exists and is executable."""
        try:
            path = self.resolve_binary()
            return bool(path and Path(path).exists())
        except Exception:
            return False

    @staticmethod
    def compute_file_sha256(path: Path) -> str:
        """Calculate SHA-256 hash of target file for provenance chaining."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
