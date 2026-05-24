"""Log parsing utilities for FaultBench.

Parses raw agent execution logs to extract structured metrics:
- Exception/traceback counts
- First failure step
- Error patterns
- Execution phases

All log parsing is centralized here — no other module does regex
matching on log output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from faultbench.constants import TRACEBACK_MARKER
from faultbench.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ParsedLogMetrics:
    """Metrics extracted from raw agent execution logs."""

    exception_count: int
    first_failure_step: Optional[int]
    error_types: list[str]
    traceback_snippets: list[str]
    total_lines: int


# Pre-compiled patterns for performance
_TRACEBACK_PATTERN = re.compile(
    r"Traceback \(most recent call last\):", re.MULTILINE
)
_ERROR_TYPE_PATTERN = re.compile(
    r"^(\w+(?:Error|Exception|Warning)): (.+)$", re.MULTILINE
)
_STEP_PATTERN = re.compile(
    r"(?:step|iteration|action)\s*[#:]?\s*(\d+)", re.IGNORECASE
)
_FAILURE_INDICATORS = re.compile(
    r"(?:FAIL|ERROR|CRASH|EXCEPTION|ABORT|FATAL)", re.IGNORECASE
)


def parse_log_text(raw_log: str) -> ParsedLogMetrics:
    """Parse raw log text and extract structured metrics.

    Args:
        raw_log: The full text of an execution log.

    Returns:
        A :class:`ParsedLogMetrics` with extracted counts and patterns.
    """
    log.info("log_parse_start", log_length=len(raw_log))

    lines = raw_log.splitlines()
    total_lines = len(lines)

    # Count tracebacks
    traceback_matches = _TRACEBACK_PATTERN.findall(raw_log)
    exception_count = len(traceback_matches)

    # Extract error types (e.g., "TypeError: unsupported operand")
    error_type_matches = _ERROR_TYPE_PATTERN.findall(raw_log)
    error_types: list[str] = []
    for error_class, _message in error_type_matches:
        if error_class not in error_types:
            error_types.append(error_class)

    # Extract traceback snippets (up to 10 lines each)
    traceback_snippets = _extract_traceback_snippets(lines)

    # Find the first step that shows a failure
    first_failure_step = _find_first_failure_step(raw_log)

    metrics = ParsedLogMetrics(
        exception_count=exception_count,
        first_failure_step=first_failure_step,
        error_types=error_types,
        traceback_snippets=traceback_snippets,
        total_lines=total_lines,
    )

    log.info(
        "log_parse_complete",
        exception_count=metrics.exception_count,
        first_failure_step=metrics.first_failure_step,
        error_types_found=len(metrics.error_types),
        total_lines=metrics.total_lines,
    )

    return metrics


def parse_log_file(log_path: Path) -> ParsedLogMetrics:
    """Parse a log file from disk.

    Args:
        log_path: Path to the log file.

    Returns:
        Parsed metrics.

    Raises:
        FileNotFoundError: If the log file does not exist.
    """
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    raw_text = log_path.read_text(encoding="utf-8", errors="replace")
    return parse_log_text(raw_text)


def _extract_traceback_snippets(
    lines: list[str], max_snippets: int = 20, snippet_lines: int = 10
) -> list[str]:
    """Extract traceback snippets from log lines.

    Captures up to ``snippet_lines`` lines starting from each
    "Traceback" marker.

    Args:
        lines: All log lines.
        max_snippets: Maximum number of snippets to collect.
        snippet_lines: Number of lines per snippet.

    Returns:
        List of traceback snippet strings.
    """
    snippets: list[str] = []

    for i, line in enumerate(lines):
        if TRACEBACK_MARKER in line:
            end = min(i + snippet_lines, len(lines))
            snippet = "\n".join(lines[i:end])
            snippets.append(snippet)
            if len(snippets) >= max_snippets:
                break

    return snippets


def _find_first_failure_step(raw_log: str) -> Optional[int]:
    """Find the first step/iteration number associated with a failure.

    Scans for failure indicators near step markers and returns the
    lowest step number where a failure occurred.

    Args:
        raw_log: Full log text.

    Returns:
        Step number of the first failure, or ``None`` if not found.
    """
    # Split into chunks around failure indicators
    failure_positions = [
        m.start() for m in _FAILURE_INDICATORS.finditer(raw_log)
    ]

    if not failure_positions:
        return None

    # For each failure, look backward for the nearest step number
    first_failure: Optional[int] = None

    for pos in failure_positions:
        # Search in a window around the failure indicator
        window_start = max(0, pos - 500)
        window = raw_log[window_start:pos + 200]

        step_matches = _STEP_PATTERN.findall(window)
        if step_matches:
            # Take the last step number before the failure
            step_num = int(step_matches[-1])
            if first_failure is None or step_num < first_failure:
                first_failure = step_num

    return first_failure


def count_pattern_occurrences(raw_log: str, pattern: str) -> int:
    """Count occurrences of a regex pattern in log text.

    Args:
        raw_log: Full log text.
        pattern: Regular expression pattern.

    Returns:
        Number of matches.
    """
    try:
        compiled = re.compile(pattern, re.MULTILINE | re.IGNORECASE)
        return len(compiled.findall(raw_log))
    except re.error as exc:
        log.warning("invalid_regex_pattern", pattern=pattern, error=str(exc))
        return 0
