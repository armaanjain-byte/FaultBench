"""FaultBench — Stress-test coding agents under adversarial runtime conditions.

FaultBench is a benchmarking framework that measures the robustness of
autonomous coding agents when operating under environmental instability.
It injects controlled mutations into task repositories, executes agents
inside isolated Docker sandboxes, and collects execution metrics to
produce reproducible degradation reports.
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "FaultBench Contributors"
