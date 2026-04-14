"""Generate a Markdown validation report."""

from __future__ import annotations

from pathlib import Path

from ..models import ActionType, ChunkStatus, ValidationResult


_STATUS_EMOJIS = {
    ChunkStatus.INVALID: "❌",
    ChunkStatus.OUTDATED: "⚠️",
    ChunkStatus.DUPLICATE: "🔁",
    ChunkStatus.ORPHANED: "🔗",
    ChunkStatus.EMPTY: "📭",
}

_ACTION_LABELS = {
    ActionType.DELETE: "delete",
    ActionType.ARCHIVE: "archive",
    ActionType.FIX: "fix needed",
    ActionType.FLAG: "review",
}


class MarkdownReporter:
    """Generate a Markdown report of validation results."""

    def report(self, result: ValidationResult, output: Path):
        """Write validation report to a Markdown file."""
        result.update_counts()
        lines = self._build_report_lines(result)
        output.write_text("\n".join(lines), encoding="utf-8")

    def _build_report_lines(self, result: ValidationResult) -> list[str]:
        lines: list[str] = []
        lines.extend(self._build_summary_lines(result))
        lines.extend(self._build_issue_lines(result))
        lines.extend(self._build_action_lines(result))
        return lines

    def _build_summary_lines(self, result: ValidationResult) -> list[str]:
        total = result.chunks_total
        valid_pct = result.chunks_valid / total * 100 if total else 0
        lines = [
            "# Documentation validation report",
            "",
            f"**Files scanned:** {result.files_scanned}  ",
            f"**Total sections:** {total}  ",
            f"**Health:** {valid_pct:.0f}% valid",
            "",
            "| Status | Count |",
            "|--------|------:|",
        ]

        for label, count in [
            ("Valid", result.chunks_valid),
            ("Outdated", result.chunks_outdated),
            ("Invalid", result.chunks_invalid),
            ("Duplicate", result.chunks_duplicate),
            ("Orphaned", result.chunks_orphaned),
            ("Empty", result.chunks_empty),
        ]:
            if count > 0:
                lines.append(f"| {label} | {count} |")

        lines.append("")
        return lines

    def _build_issue_lines(self, result: ValidationResult) -> list[str]:
        lines: list[str] = []
        files_with_issues = [
            doc_file
            for doc_file in result.doc_files
            if any(chunk.status != ChunkStatus.VALID for chunk in doc_file.chunks)
        ]

        if not files_with_issues:
            return lines

        lines.extend(["## Issues by file", ""])
        for doc_file in files_with_issues:
            lines.append(f"### `{doc_file.relative_path}`")
            lines.append("")

            for chunk in doc_file.chunks:
                if chunk.status == ChunkStatus.VALID:
                    continue

                status_emoji = _STATUS_EMOJIS.get(chunk.status, "❓")
                action_label = _ACTION_LABELS.get(chunk.action, "keep")
                lines.append(
                    f"- {status_emoji} **L{chunk.line_start}–{chunk.line_end}** "
                    f"`{chunk.heading}` → {chunk.status.value} ({action_label})"
                )

                for issue in chunk.issues:
                    lines.append(f"  - {issue.message}")
                    if issue.suggestion:
                        lines.append(f"    - 💡 {issue.suggestion}")

            lines.append("")

        return lines

    def _build_action_lines(self, result: ValidationResult) -> list[str]:
        actions = {a: 0 for a in ActionType}
        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                actions[chunk.action] += 1

        lines = ["## Recommended actions", ""]
        for action, count in actions.items():
            if count > 0 and action != ActionType.KEEP:
                lines.append(f"- **{action.value}**: {count} section(s)")
        lines.append("")
        return lines
