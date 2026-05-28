from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MutationReport:
    mutation_name: str
    tests_affected: int = 0
    failures_expected: int = 0
    failures_actual: int = 0
    behavior_matched: bool = True
    rollback_successful: bool = True


def render_terminal_summary(reports: list[MutationReport]) -> str:
    lines = ["================ FaultBench Summary ================", ""]

    for index, report in enumerate(reports):
        if index:
            lines.append("")
        lines.extend(
            [
                f"Mutation: {report.mutation_name}",
                f"Tests affected: {report.tests_affected}",
                f"Failures expected: {report.failures_expected}",
                f"Failures actual: {report.failures_actual}",
                f"Behavior matched expectation: {'YES' if report.behavior_matched else 'NO'}",
                f"Rollback successful: {'YES' if report.rollback_successful else 'NO'}",
            ]
        )

    return "\n".join(lines)

