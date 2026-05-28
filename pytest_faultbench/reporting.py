from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MutationReport:
    mutation_name: str
    tests_affected: int
    failures_detected: bool
    rollback_successful: bool


def render_terminal_summary(reports: list[MutationReport]) -> str:
    lines = ["================ FaultBench Summary ================", ""]

    for index, report in enumerate(reports):
        if index:
            lines.append("")
        lines.extend(
            [
                f"Mutation: {report.mutation_name}",
                f"Tests affected: {report.tests_affected}",
                f"Failures detected: {'YES' if report.failures_detected else 'NO'}",
                f"Rollback successful: {'YES' if report.rollback_successful else 'NO'}",
            ]
        )

    return "\n".join(lines)
