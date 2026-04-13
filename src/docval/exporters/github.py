"""Export docval results to GitHub Issues."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ValidationResult, DocChunk


class GitHubExporter:
    """Export validation results to GitHub Issues."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str | None = None,
        dry_run: bool = True,
    ):
        self.owner = owner
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.dry_run = dry_run
        self._github = None
        self._repo_obj = None

    def _get_github(self):
        """Lazy initialization of GitHub client."""
        if self._github is None:
            try:
                from github import Github
            except ImportError:
                raise ImportError(
                    "PyGithub is required. Install with: pip install PyGithub"
                )

            if not self.token:
                raise ValueError(
                    "GitHub token required. Set GITHUB_TOKEN env var or pass token="
                )

            self._github = Github(self.token)
            self._repo_obj = self._github.get_repo(f"{self.owner}/{self.repo}")

        return self._github, self._repo_obj

    def export(self, result: "ValidationResult") -> list[dict]:
        """Export validation results to GitHub Issues.

        Args:
            result: ValidationResult from docval scan

        Returns:
            List of created/updated issue info
        """
        if self.dry_run:
            return self._preview_export(result)

        # Only import PyGithub when actually needed (not in dry-run)
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
        """Actually create/update GitHub issues."""
        _, repo = self._get_github()
        created = []
        counter = 0

        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if not chunk.issues:
                    continue

                counter += 1
                task_id = f"DOC-{counter:03d}"

                title = self._generate_title(chunk)
                body = self._generate_body(chunk, task_id)
                labels = self._generate_labels(chunk)

                try:
                    # Check if issue already exists by title
                    existing = self._find_existing_issue(repo, title)

                    if existing:
                        # Update existing issue
                        issue = existing
                        created.append({
                            "id": task_id,
                            "github_number": issue.number,
                            "url": issue.html_url,
                            "status": "updated",
                        })
                    else:
                        # Create new issue
                        issue = repo.create_issue(
                            title=title,
                            body=body,
                            labels=labels,
                        )
                        created.append({
                            "id": task_id,
                            "github_number": issue.number,
                            "url": issue.html_url,
                            "status": "created",
                        })

                except Exception as e:
                    created.append({
                        "id": task_id,
                        "error": str(e),
                        "status": "failed",
                    })

        return created

    def _find_existing_issue(self, repo, title: str):
        """Find existing issue by title prefix."""
        try:
            issues = repo.get_issues(state="all")
            for issue in issues:
                # Match by title prefix (without the DOC-XXX part)
                title_base = title.split(":")[-1].strip()
                if title_base in issue.title:
                    return issue
        except Exception:
            pass
        return None

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

    def _generate_body(self, chunk: "DocChunk", task_id: str) -> str:
        """Generate issue body."""
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
            labels.append("priority-critical")
        elif any(s == Severity.WARNING for s in severities):
            labels.append("priority-high")
        else:
            labels.append("priority-normal")

        return list(set(labels))  # Deduplicate

    def sync_from_planfile(self, planfile_path: "Path") -> list[dict]:
        """Sync tickets from planfile.yaml to GitHub."""
        import yaml

        content = planfile_path.read_text(encoding="utf-8")
        planfile = yaml.safe_load(content)

        results = []
        tickets = planfile.get("tickets", {})

        for ticket_id, ticket_data in tickets.items():
            # Skip if already synced
            if ticket_data.get("sync", {}).get("github"):
                results.append({
                    "id": ticket_id,
                    "status": "already-synced",
                    "github_issue": ticket_data["sync"]["github"],
                })
                continue

            if self.dry_run:
                results.append({
                    "id": ticket_id,
                    "status": "would-create",
                    "title": ticket_data.get("title", ""),
                })
                continue

            # Create issue
            try:
                _, repo = self._get_github()
                issue = repo.create_issue(
                    title=ticket_data.get("title", ""),
                    body=ticket_data.get("description", ""),
                    labels=ticket_data.get("labels", []),
                )

                results.append({
                    "id": ticket_id,
                    "status": "created",
                    "github_number": issue.number,
                    "url": issue.html_url,
                })

            except Exception as e:
                results.append({
                    "id": ticket_id,
                    "status": "failed",
                    "error": str(e),
                })

        return results
