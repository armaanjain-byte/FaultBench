"""Verification helper for the hello_world benchmark task.

Runs hello.py and checks that the output is exactly "hello world".

Exit codes:
  0 — success (output matches expected)
  1 — failure (wrong output or script error)
"""

import subprocess
import sys


def main() -> int:
    expected = "hello world"
    try:
        result = subprocess.run(
            [sys.executable, "hello.py"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        print(f"ERROR: Could not run hello.py: {exc}", file=sys.stderr)
        return 1

    actual = result.stdout.strip()
    if result.returncode != 0:
        print(f"FAIL: hello.py exited with code {result.returncode}", file=sys.stderr)
        print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
        return 1

    if actual == expected:
        print(f"PASS: output is '{actual}'")
        return 0
    else:
        print(f"FAIL: expected '{expected}', got '{actual}'", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
