"""Export docval results to GitLab Issues."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ValidationResult, DocChunk


class GitLabExporter:
    """Export validation results to GitLab Issues."""

    def __init__(
        self,
        project_id: str | int,
        token: str | None = None,
        url: str = "https://gitlab.com",
        dry_run: bool = True,
    ):
        self.project_id = project_id
        self.token = token or os.environ.get("GITLAB_TOKEN")
        self.url = url.rstrip("/")
        self.dry_run = dry_run

    def export(self, result: "ValidationResult") -> list[dict]:
        """Export validation results to GitLab Issues.

        Args:
            result: ValidationResult from docval scan

        Returns:
            List of created/updated issue info
        """
        if self.dry_run:
            return self._preview_export(result)

        # Only import requests when actually needed (not in dry-run)
        return self._execute_export(result)

    def _preview_export(self, result: "ValidationResult") -> list[dict]:
        """Preview what would be exported."""
        preview = []
        counter = 0

        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if not chunk.issues:
                    continue

                counter += 1
                task_id = f"DOC-{counter:03d}"

                title = self._generate_title(chunk)
                labels = self._generate_labels(chunk)

                preview.append({
                    "id": task_id,
                    "title": title,
                    "labels": labels,
                    "would_create": True,
                    "file": str(chunk.file),
                    "line": chunk.line_start,
                })

        return preview

    def _execute_export(self, result: "ValidationResult") -> list[dict]:
        """Actually create GitLab issues."""
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests is required. Install with: pip install requests"
            )

        if not self.token:
            raise ValueError(
                "GitLab token required. Set GITLAB_TOKEN env var or pass token="
            )

        created = []
        counter = 0

        headers = {
            "Private-Token": self.token,
            "Content-Type": "application/json",
        }

        api_url = f"{self.url}/api/v4/projects/{self.project_id}/issues"

        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if not chunk.issues:
                    continue

                counter += 1
                task_id = f"DOC-{counter:03d}"

                title = self._generate_title(chunk)
                description = self._generate_description(chunk, task_id)
                labels = ",".join(self._generate_labels(chunk))

                try:
                    response = requests.post(
                        api_url,
                        headers=headers,
                        json={
                            "title": title,
                            "description": description,
                            "labels": labels,
                        },
                        timeout=30,
                    )

                    if response.status_code == 201:
                        data = response.json()
                        created.append({
                            "id": task_id,
                            "gitlab_iid": data.get("iid"),
                            "url": data.get("web_url"),
                            "status": "created",
                        })
                    else:
                        created.append({
                            "id": task_id,
                            "status": "failed",
                            "error": f"HTTP {response.status_code}: {response.text}",
                        })

                except Exception as e:
                    created.append({
                        "id": task_id,
                        "status": "failed",
                        "error": str(e),
                    })

        return created

    def _generate_title(self, chunk: "DocChunk") -> str:
        """Generate issue title."""
        action_map = {
            "broken_link": "[Docs] Fix broken link",
            "empty": "[Docs] Remove empty section",
            "outdated_marker": "[Docs] Update deprecated content",
            "orphaned_code_ref": "[Docs] Fix code reference",
            "duplicate": "[Docs] Remove duplicate content",
        }

        if chunk.issues:
            base = action_map.get(chunk.issues[0].rule, "[Docs] Fix documentation issue")
        else:
            base = "[Docs] Fix documentation"

        if chunk.heading:
            return f"{base}: {chunk.heading}"

        return base

    def _generate_description(self, chunk: "DocChunk", task_id: str) -> str:
        """Generate issue description."""
        lines = [
            f"## Task ID: {task_id}",
            "",
            f"**File**: `{chunk.file}`",
            f"**Section**: {chunk.heading or '(no heading)'}",
            f"**Lines**: {chunk.line_start}-{chunk.line_end}",
            "",
            "## Issues Found",
            "",
        ]

        for issue in chunk.issues:
            lines.append(f"- **{issue.rule}**: {issue.message}")
            if issue.suggestion:
                lines.append(f"  - 💡 {issue.suggestion}")

        lines.extend([
            "",
            "## Suggested Action",
            "",
            f"Action: `{chunk.action.value if chunk.action else 'review'}`",
            f"Confidence: {chunk.confidence:.0%}",
            "",
            "---",
            "",
            "*Auto-generated by docval*",
        ])

        return "\n".join(lines)

    def _generate_labels(self, chunk: "DocChunk") -> list[str]:
        """Generate labels for the issue."""
        labels = ["documentation", "docval"]

        # Add issue type labels
        for issue in chunk.issues:
            if issue.rule == "broken_link":
                labels.append("broken-link")
            elif issue.rule == "empty":
                labels.append("cleanup")
            elif issue.rule == "outdated_marker":
                labels.append("outdated")
            elif issue.rule == "orphaned_code_ref":
                labels.append("code-ref")

        # Add priority label
        from ..models import Severity
        severities = [i.severity for i in chunk.issues]

        if any(s in (Severity.CRITICAL, Severity.ERROR) for s in severities):
            labels.append("priority::critical")
        elif any(s == Severity.WARNING for s in severities):
            labels.append("priority::high")
        else:
            labels.append("priority::normal")

        return list(set(labels))  # Deduplicate
