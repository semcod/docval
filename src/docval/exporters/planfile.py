"""Export docval results to planfile.yaml format."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from ..models import ValidationResult, DocChunk, Issue


class PlanfileExporter:
    """Export validation results to planfile.yaml format."""

    def __init__(
        self,
        project_name: str = "docval",
        version: str = "0.1.1",
        github_owner: str | None = None,
        github_repo: str | None = None,
    ):
        self.project_name = project_name
        self.version = version
        self.github_owner = github_owner
        self.github_repo = github_repo
        self.generated_at = datetime.utcnow()

    def export(
        self,
        result: "ValidationResult",
        output_path: Path | None = None,
        sprint_id: str = "doc-cleanup",
    ) -> str:
        """Export validation result to planfile.yaml format.

        Args:
            result: ValidationResult from docval scan
            output_path: Optional path to write the file
            sprint_id: Sprint identifier

        Returns:
            The planfile.yaml content as string
        """
        planfile = self._build_planfile(result, sprint_id)
        content = yaml.safe_dump(
            planfile,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

        if output_path:
            output_path.write_text(content, encoding="utf-8")

        return content

    def _build_planfile(self, result: "ValidationResult", sprint_id: str) -> dict:
        """Build planfile dictionary structure."""
        tickets = self._extract_tickets(result, sprint_id)

        # Count issues by type
        issues_by_type: dict[str, int] = {}
        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                for issue in chunk.issues:
                    issues_by_type[issue.rule] = issues_by_type.get(issue.rule, 0) + 1

        planfile = {
            "project": {
                "name": self.project_name,
                "version": self.version,
                "source": "docval-scan",
                "generated_at": self.generated_at.isoformat() + "Z",
            },
            "integrations": {
                "github": {
                    "enabled": bool(self.github_owner and self.github_repo),
                    "owner": self.github_owner or "",
                    "repo": self.github_repo or "",
                    "label_prefix": "doc-",
                    "auto_sync": False,
                },
                "gitlab": {
                    "enabled": False,
                    "project_id": None,
                    "auto_sync": False,
                },
            },
            "current_sprint": {
                "id": sprint_id,
                "goal": "Clean up documentation based on docval validation",
                "start_date": self.generated_at.strftime("%Y-%m-%d"),
                "end_date": "",
                "status": "active",
            },
            "tickets": tickets,
            "backlog": [],
            "sync": {
                "github": {
                    "enabled": False,
                    "last_sync": None,
                    "ticket_map": {},
                },
                "gitlab": {
                    "enabled": False,
                    "last_sync": None,
                    "ticket_map": {},
                },
            },
            "metadata": {
                "docval_version": self.version,
                "scan_date": self.generated_at.strftime("%Y-%m-%d"),
                "files_scanned": result.files_scanned,
                "total_issues": sum(len(f.chunks) for f in result.doc_files),
                "health_score": self._calculate_health_score(result),
                "issues_by_type": issues_by_type,
            },
        }

        return planfile

    def _extract_tickets(
        self, result: "ValidationResult", sprint_id: str
    ) -> dict[str, dict]:
        """Extract tickets from validation result."""
        tickets: dict[str, dict] = {}
        task_counter = 0

        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if not chunk.issues:
                    continue

                task_counter += 1
                task_id = f"DOC-{task_counter:03d}"

                # Group issues for this chunk
                issue_descriptions = []
                labels = set()
                acceptance_criteria = []

                for issue in chunk.issues:
                    issue_descriptions.append(issue.message)
                    labels.add(issue.rule)
                    if issue.suggestion:
                        acceptance_criteria.append(issue.suggestion)

                priority = self._map_priority(chunk)

                ticket = {
                    "id": task_id,
                    "title": self._generate_title(chunk, issue_descriptions[0]),
                    "description": "\n".join(issue_descriptions),
                    "status": "open",
                    "priority": priority,
                    "sprint": sprint_id,
                    "labels": list(labels) + ["documentation", "auto-generated"],
                    "acceptance_criteria": acceptance_criteria or ["Issue is resolved"],
                    "source": {
                        "tool": "docval",
                        "file": str(chunk.file),
                        "line_start": chunk.line_start,
                        "line_end": chunk.line_end,
                        "issue_type": chunk.issues[0].rule if chunk.issues else "unknown",
                        "issue_count": len(chunk.issues),
                    },
                    "actions": [
                        {
                            "type": chunk.action.value if chunk.action else "flag",
                            "confidence": chunk.confidence,
                        }
                    ],
                    "sync": {},
                }

                tickets[task_id] = ticket

        return tickets

    def _generate_title(self, chunk: "DocChunk", first_issue: str) -> str:
        """Generate ticket title."""
        action_map = {
            "broken_link": "Fix broken link",
            "empty": "Remove empty section",
            "outdated_marker": "Update deprecated content",
            "orphaned_code_ref": "Fix code reference",
            "duplicate": "Remove duplicate",
        }

        base = action_map.get(chunk.issues[0].rule, "Fix documentation issue") if chunk.issues else "Fix documentation"

        if chunk.heading:
            return f"{base}: {chunk.heading}"

        return base

    def _map_priority(self, chunk: "DocChunk") -> str:
        """Map chunk status to planfile priority."""
        from ..models import Severity

        severities = [i.severity for i in chunk.issues]

        if any(s in (Severity.CRITICAL, Severity.ERROR) for s in severities):
            return "critical"
        if chunk.status.value in ("invalid", "orphaned"):
            return "critical"
        if chunk.status.value == "outdated":
            return "high"
        if any(s == Severity.WARNING for s in severities):
            return "high"

        return "normal"

    def _calculate_health_score(self, result: "ValidationResult") -> float:
        """Calculate overall health score."""
        if not result.chunks_total:
            return 1.0

        valid = result.chunks_valid
        return round(valid / result.chunks_total, 2)
