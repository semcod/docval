"""Export docval results to TODO.md format."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ValidationResult, DocChunk, DocFile, Issue


@dataclass
class TodoTask:
    """A single task for the TODO list."""
    id: str
    title: str
    file: str
    section: str
    line_start: int
    line_end: int
    priority: str  # critical, high, medium, low
    action: str  # fix, delete, archive, flag
    issue_type: str
    description: str
    suggestion: str
    labels: list[str]


class TodoExporter:
    """Export validation results to TODO.md format."""

    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def __init__(self, version: str = "0.1.1"):
        self.version = version
        self.generated_at = datetime.utcnow()

    def export(self, result: "ValidationResult", output_path: Path | None = None) -> str:
        """Export validation result to TODO.md format.

        Args:
            result: ValidationResult from docval scan
            output_path: Optional path to write the file

        Returns:
            The TODO.md content as string
        """
        tasks = self._extract_tasks(result)
        content = self._generate_todo_md(tasks)

        if output_path:
            output_path.write_text(content, encoding="utf-8")

        return content

    def _extract_tasks(self, result: "ValidationResult") -> list[TodoTask]:
        """Extract tasks from validation result."""
        tasks: list[TodoTask] = []
        task_counter = 0

        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if not chunk.issues:
                    continue

                # Determine priority based on issue severity
                priority = self._determine_priority(chunk)
                action = chunk.action.value if chunk.action else "flag"

                # Group issues by type
                for issue in chunk.issues:
                    task_counter += 1
                    task_id = f"DOC-{task_counter:03d}"

                    task = TodoTask(
                        id=task_id,
                        title=self._generate_title(chunk, issue),
                        file=str(chunk.file),
                        section=chunk.heading,
                        line_start=chunk.line_start,
                        line_end=chunk.line_end,
                        priority=priority,
                        action=action,
                        issue_type=issue.rule,
                        description=issue.message,
                        suggestion=issue.suggestion or "",
                        labels=self._generate_labels(chunk, issue, action),
                    )
                    tasks.append(task)

        # Sort by priority
        tasks.sort(key=lambda t: self.PRIORITY_ORDER.get(t.priority, 99))
        return tasks

    def _determine_priority(self, chunk: "DocChunk") -> str:
        """Determine task priority from chunk issues."""
        from ..models import Severity

        severities = [i.severity for i in chunk.issues]

        if any(s == Severity.CRITICAL for s in severities):
            return "critical"
        if any(s == Severity.ERROR for s in severities):
            return "critical"
        if chunk.status.value in ("invalid", "orphaned"):
            return "critical"
        if chunk.status.value == "outdated":
            return "high"
        if chunk.status.value == "empty":
            return "high"
        if any(s == Severity.WARNING for s in severities):
            return "high"

        return "medium"

    def _generate_title(self, chunk: "DocChunk", issue: "Issue") -> str:
        """Generate task title from chunk and issue."""
        action_map = {
            "broken_link": "Fix broken internal link",
            "empty": "Delete empty section",
            "outdated_marker": "Update deprecated content",
            "orphaned_code_ref": "Fix orphaned code reference",
            "duplicate": "Remove duplicate content",
            "todo_marker": "Review TODO/FIXME marker",
        }

        base = action_map.get(issue.rule, f"Fix {issue.rule}")

        # Add context for broken links
        if issue.rule == "broken_link":
            # Extract filename from message
            import re
            match = re.search(r": (.+)$", issue.message)
            if match:
                return f"{base}: {match.group(1)}"

        # Add section name for empty sections
        if issue.rule == "empty" and chunk.heading:
            return f"{base}: {chunk.heading}"

        return base

    def _generate_labels(self, chunk: "DocChunk", issue: "Issue", action: str) -> list[str]:
        """Generate labels for the task."""
        labels = [issue.rule, "documentation", "auto-generated"]

        if action:
            labels.append(action)

        if chunk.status.value == "outdated":
            labels.append("outdated")
        if chunk.status.value == "empty":
            labels.append("empty-section")

        return labels

    def _generate_todo_md(self, tasks: list[TodoTask]) -> str:
        """Generate TODO.md content."""
        lines = [
            "# Docval Refactoring Tasks",
            "",
            "> Auto-generated from docval scan. Synchronize with: `docval sync-planfile`",
            "",
            "## Overview",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Tasks | {len(tasks)} |",
        ]

        # Count by priority
        critical = sum(1 for t in tasks if t.priority == "critical")
        high = sum(1 for t in tasks if t.priority == "high")
        medium = sum(1 for t in tasks if t.priority == "medium")
        low = sum(1 for t in tasks if t.priority == "low")

        lines.extend([
            f"| Critical | {critical} |",
            f"| High | {high} |",
            f"| Medium | {medium} |",
            f"| Low | {low} |",
            "",
        ])

        # Group by priority
        current_priority = None
        for task in tasks:
            if task.priority != current_priority:
                current_priority = task.priority
                lines.extend([
                    "",
                    f"## {current_priority.upper()} Priority",
                    "",
                ])

            lines.extend(self._format_task(task))

        # Add footer
        lines.extend([
            "",
            "---",
            "",
            "## Commands",
            "",
            "### Update this TODO from scan",
            "```bash",
            "docval scan docs/ -o TODO.md --format todo",
            "```",
            "",
            "### Sync to planfile.yaml",
            "```bash",
            "docval sync-planfile --export-yaml",
            "```",
            "",
            "### Sync to GitHub Issues",
            "```bash",
            "docval sync-planfile --github-owner wronai --github-repo docval",
            "```",
            "",
            "### Apply all auto-fixes",
            "```bash",
            "docval fix docs/ --project . --no-dry-run",
            "```",
            "",
            "---",
            "",
            f"*Generated by docval v{self.version} on {self.generated_at.strftime('%Y-%m-%d')}*",
            "",
        ])

        return "\n".join(lines)

    def _format_task(self, task: TodoTask) -> list[str]:
        """Format a single task in Markdown."""
        lines = [
            f"### [{task.id}] {task.title}",
            f"- **File**: `{task.file}:{task.line_start}-{task.line_end}`",
            f"- **Section**: {task.section}",
            f"- **Issue**: {task.description}",
            f"- **Action**: {task.action}",
        ]

        if task.suggestion:
            lines.append(f"- **Suggestion**: {task.suggestion}")

        lines.append(f"- **Labels**: {', '.join(task.labels)}")
        lines.append("")

        return lines
