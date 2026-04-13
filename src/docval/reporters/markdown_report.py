"""Generate a Markdown validation report."""

from __future__ import annotations

from pathlib import Path

from ..models import ActionType, ChunkStatus, DocFile, ValidationResult


class MarkdownReporter:
    """Generate a Markdown report of validation results."""

    def report(self, result: ValidationResult, output: Path):
        """Write validation report to a Markdown file."""
        result.update_counts()
        lines: list[str] = []

        lines.append("# Documentation validation report")
        lines.append("")
        total = result.chunks_total
        valid_pct = result.chunks_valid / total * 100 if total else 0
        lines.append(f"**Files scanned:** {result.files_scanned}  ")
        lines.append(f"**Total sections:** {total}  ")
        lines.append(f"**Health:** {valid_pct:.0f}% valid")
        lines.append("")

        # Summary table
        lines.append("| Status | Count |")
        lines.append("|--------|------:|")
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

        # Issues by file
        files_with_issues = [
            f for f in result.doc_files
            if any(c.status != ChunkStatus.VALID for c in f.chunks)
        ]

        if files_with_issues:
            lines.append("## Issues by file")
            lines.append("")

            for doc_file in files_with_issues:
                lines.append(f"### `{doc_file.relative_path}`")
                lines.append("")

                for chunk in doc_file.chunks:
                    if chunk.status == ChunkStatus.VALID:
                        continue

                    status_emoji = {
                        ChunkStatus.INVALID: "❌",
                        ChunkStatus.OUTDATED: "⚠️",
                        ChunkStatus.DUPLICATE: "🔁",
                        ChunkStatus.ORPHANED: "🔗",
                        ChunkStatus.EMPTY: "📭",
                    }.get(chunk.status, "❓")

                    action_label = {
                        ActionType.DELETE: "delete",
                        ActionType.ARCHIVE: "archive",
                        ActionType.FIX: "fix needed",
                        ActionType.FLAG: "review",
                    }.get(chunk.action, "keep")

                    lines.append(
                        f"- {status_emoji} **L{chunk.line_start}–{chunk.line_end}** "
                        f"`{chunk.heading}` → {chunk.status.value} ({action_label})"
                    )

                    for issue in chunk.issues:
                        lines.append(f"  - {issue.message}")
                        if issue.suggestion:
                            lines.append(f"    - 💡 {issue.suggestion}")

                lines.append("")

        # Action summary
        actions = {a: 0 for a in ActionType}
        for f in result.doc_files:
            for c in f.chunks:
                actions[c.action] += 1

        lines.append("## Recommended actions")
        lines.append("")
        for action, count in actions.items():
            if count > 0 and action != ActionType.KEEP:
                lines.append(f"- **{action.value}**: {count} section(s)")
        lines.append("")

        output.write_text("\n".join(lines), encoding="utf-8")
