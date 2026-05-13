"""Export docval results to toon.yaml format."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..models import Issue, Severity, ActionType, ValidationResult, DocChunk


class ToonExporter:
    """Export validation results to toon.yaml format for documentation analysis."""

    def __init__(self, project_name: str = "docval"):
        self.project_name = project_name

    def export(self, result: ValidationResult, output_path: Path) -> None:
        """Export validation results to a toon.yaml file."""
        lines = self._build_toon_lines(result)
        output_path.write_text("\n".join(lines), encoding="utf-8")

    def _build_toon_lines(self, result: ValidationResult) -> list[str]:
        """Build the toon.yaml content lines."""
        lines = []
        now = datetime.now().strftime("%Y-%m-%d")

        # Calculate metrics
        total_files = len(result.doc_files)
        total_chunks = sum(len(f.chunks) for f in result.doc_files)
        total_lines = sum(f.total_lines for f in result.doc_files)
        total_words = sum(c.word_count for f in result.doc_files for c in f.chunks)

        # Collect all issues from all chunks with file path and line info
        all_issues: list[tuple[Issue, DocChunk, str]] = []
        for f in result.doc_files:
            for c in f.chunks:
                for issue in c.issues:
                    all_issues.append((issue, c, str(c.file)))

        # Count issues by severity
        critical = sum(1 for i, _, _ in all_issues if i.severity == Severity.CRITICAL)
        high = sum(1 for i, _, _ in all_issues if i.severity == Severity.ERROR)
        medium = sum(1 for i, _, _ in all_issues if i.severity == Severity.WARNING)
        low = sum(1 for i, _, _ in all_issues if i.severity == Severity.INFO)
        total_issues = len(all_issues)

        # Count actions
        delete_actions = 0
        archive_actions = 0
        fix_actions = 0
        review_actions = 0

        for f in result.doc_files:
            for c in f.chunks:
                if c.action == ActionType.DELETE:
                    delete_actions += 1
                elif c.action == ActionType.ARCHIVE:
                    archive_actions += 1
                elif c.action == ActionType.FIX:
                    fix_actions += 1
                elif c.action == ActionType.FLAG:
                    review_actions += 1

        # Header
        lines.append(f"# docval/documentation | {total_files}f {total_lines}L | {now}")
        lines.append(
            f"# stats: {total_chunks} chunks | {total_words} words | issues: {total_issues}"
        )
        lines.append(f"# health: critical={critical} high={high} medium={medium} low={low}")
        lines.append("")

        # SUMMARY section
        lines.append("SUMMARY:")
        lines.append(f"  files:      {total_files}")
        lines.append(f"  chunks:     {total_chunks}")
        lines.append(f"  lines:      {total_lines}")
        lines.append(f"  words:      {total_words}")
        lines.append(f"  issues:     {total_issues}")
        lines.append("")

        # HEALTH section
        lines.append("HEALTH:")
        health_score = 100
        if total_chunks > 0:
            health_score = max(0, 100 - (total_issues * 100 // total_chunks))
        lines.append(f"  score:      {health_score}/100")
        lines.append(
            f"  status:     {'OK' if health_score >= 80 else 'WARNING' if health_score >= 50 else 'CRITICAL'}"
        )
        lines.append("")

        # ISSUES section - with line numbers and context
        if all_issues:
            lines.append(f"ISSUES[{total_issues}]:")
            # Sort by severity priority
            severity_order = {
                Severity.CRITICAL: 0,
                Severity.ERROR: 1,
                Severity.WARNING: 2,
                Severity.INFO: 3,
            }
            sorted_issues = sorted(all_issues, key=lambda x: severity_order.get(x[0].severity, 99))
            for issue, chunk, file_path in sorted_issues:
                symbol = (
                    "!!"
                    if issue.severity == Severity.CRITICAL
                    else "!"
                    if issue.severity == Severity.ERROR
                    else "~"
                )
                line_info = (
                    f"L{chunk.line_start}-{chunk.line_end}"
                    if chunk.line_start != chunk.line_end
                    else f"L{chunk.line_start}"
                )
                lines.append(f"  {symbol} [{issue.severity.value}] {issue.message}")
                lines.append(f"      → {file_path}:{line_info}")
                # Add heading context if available
                if chunk.heading:
                    lines.append(f"        section: '{chunk.heading}'")
                # Add suggestion if available
                if issue.suggestion:
                    lines.append(f"        hint: {issue.suggestion}")
                # Add content preview for context (first 100 chars)
                content_preview = chunk.content[:100].replace("\n", " ").strip()
                if len(chunk.content) > 100:
                    content_preview += "..."
                if content_preview:
                    lines.append(f'        context: "{content_preview}"')
            lines.append("")

        # ACTIONS section
        total_actions = delete_actions + archive_actions + fix_actions + review_actions
        if total_actions > 0:
            lines.append(f"ACTIONS[{total_actions}]:")
            if delete_actions:
                lines.append(f"  delete:   {delete_actions} chunks to delete")
            if archive_actions:
                lines.append(f"  archive:  {archive_actions} files to archive")
            if fix_actions:
                lines.append(f"  fix:      {fix_actions} chunks need content fix")
            if review_actions:
                lines.append(f"  review:   {review_actions} chunks need review")
            lines.append("")

        # REFACTOR section - with actionable LLM instructions
        lines.append("REFACTOR:")
        if total_issues == 0:
            lines.append("  [✓] Documentation is in good shape - no refactoring needed")
        else:
            # Group issues by type for specific instructions
            broken_links = [
                i
                for i, c, _ in all_issues
                if "link" in i.message.lower() or "target not found" in i.message.lower()
            ]
            empty_sections = [
                i
                for i, c, _ in all_issues
                if "no meaningful content" in i.message.lower()
                or "only a heading" in i.message.lower()
            ]
            orphan_refs = [
                i
                for i, c, _ in all_issues
                if "unknown code symbol" in i.message.lower() or "orphan" in i.message.lower()
            ]
            todos = [
                i
                for i, c, _ in all_issues
                if "TODO" in i.message.upper() or "FIXME" in i.message.upper()
            ]

            task_num = 1

            # Broken links - specific instructions
            if broken_links:
                unique_links = set()
                for i in broken_links:
                    # Extract link target from message like "Internal link target not found: ./CONTRIBUTING.md"
                    if "target not found" in i.message:
                        target = i.message.split("target not found:")[-1].strip()
                        unique_links.add(target)
                lines.append(
                    f"  [{task_num}] ○ fix_broken_links | {len(broken_links)} broken internal links"
                )
                for link in sorted(unique_links)[:5]:  # Show first 5
                    lines.append(f"      → Create or fix: {link}")
                if len(unique_links) > 5:
                    lines.append(f"      → ... and {len(unique_links) - 5} more")
                task_num += 1

            # Empty sections
            if empty_sections:
                lines.append(
                    f"  [{task_num}] ○ remove_empty_sections | {len(empty_sections)} empty/placeholder sections"
                )
                lines.append("      → Delete sections with no content or add meaningful text")
                task_num += 1

            # Orphan references
            if orphan_refs:
                lines.append(
                    f"  [{task_num}] ○ fix_orphan_refs | {len(orphan_refs)} references to unknown symbols"
                )
                lines.append("      → Update references to match actual codebase symbols")
                task_num += 1

            # TODO markers
            if todos:
                lines.append(f"  [{task_num}] ○ resolve_todos | {len(todos)} TODO/FIXME markers")
                lines.append("      → Implement or remove TODO items")
                task_num += 1

            # Action-based tasks
            if delete_actions > 0:
                lines.append(
                    f"  [{task_num}] ○ delete_obsolete | {delete_actions} chunks marked for deletion"
                )
                lines.append("      → Run: docval fix docs/ --no-dry-run to auto-delete")
                task_num += 1

            if fix_actions > 0:
                lines.append(
                    f"  [{task_num}] ○ fix_content | {fix_actions} chunks need content rewrite"
                )
                lines.append("      → Use LLM to rewrite outdated content based on current code")
                task_num += 1

            # Generic remaining issues
            remaining = (
                total_issues
                - len(broken_links)
                - len(empty_sections)
                - len(orphan_refs)
                - len(todos)
            )
            if remaining > 0:
                lines.append(
                    f"  [{task_num}] ○ review_other | {remaining} other issues to review manually"
                )

        lines.append("")

        # METRICS-TARGET section
        lines.append("METRICS-TARGET:")
        lines.append(f"  issues:     {total_issues} → 0")
        lines.append(f"  health:     {health_score}/100 → 100/100")
        lines.append("")

        # DOCUMENTATION-BY-STATUS section
        status_ok = sum(
            1 for f in result.doc_files for c in f.chunks if c.action == ActionType.KEEP
        )
        if total_chunks > 0:
            lines.append("DOCUMENTATION:")
            lines.append(f"  ok:        {status_ok} chunks ({status_ok * 100 // total_chunks}%)")
            if total_actions > 0:
                lines.append(
                    f"  needs_fix: {total_actions} chunks ({total_actions * 100 // total_chunks}%)"
                )
            lines.append("")

        # EVOLUTION
        lines.append("EVOLUTION:")
        lines.append(
            f"  {now} {total_files}f {total_lines}L {total_issues}i {health_score}% // docval scan"
        )
        lines.append("")

        return lines
