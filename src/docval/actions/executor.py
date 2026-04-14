"""Execute validated actions on documentation files.

Supports: delete sections, archive files, generate fix patches.
All destructive operations require explicit confirmation or --force flag.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..models import ActionType, ChunkStatus, DocFile


@dataclass
class ActionResult:
    """Summary of executed actions."""
    deleted_chunks: int = 0
    archived_files: int = 0
    fixed_chunks: int = 0
    flagged_chunks: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class _ActionPlan:
    files_to_archive: list[DocFile] = field(default_factory=list)
    files_with_deletions: dict[Path, list[tuple[int, int]]] = field(default_factory=dict)


class ActionExecutor:
    """Execute remediation actions on doc files."""

    def __init__(
        self,
        archive_dir: Path | None = None,
        dry_run: bool = True,
    ):
        self.archive_dir = archive_dir or Path("docs/_archive")
        self.dry_run = dry_run

    def execute(self, doc_files: list[DocFile], base_dir: Path) -> ActionResult:
        """Apply all pending actions. Returns summary."""
        result = ActionResult()
        plan = self._collect_actions(doc_files, result)

        if self.dry_run:
            return result

        self._apply_deletions(plan.files_with_deletions, result)
        self._apply_archives(plan.files_to_archive, base_dir, result)

        return result

    def _collect_actions(self, doc_files: list[DocFile], result: ActionResult) -> _ActionPlan:
        """Collect all requested actions into a reusable execution plan."""
        plan = _ActionPlan()

        for doc_file in doc_files:
            if self._should_archive_file(doc_file):
                plan.files_to_archive.append(doc_file)

            for chunk in doc_file.chunks:
                self._record_chunk_action(doc_file, chunk, plan, result)

        return plan

    def _should_archive_file(self, doc_file: DocFile) -> bool:
        """Return True when every actionable chunk in a file is archived."""
        return bool(doc_file.chunks) and all(
            c.action == ActionType.ARCHIVE for c in doc_file.chunks if c.issues
        )

    def _record_chunk_action(
        self,
        doc_file: DocFile,
        chunk,
        plan: _ActionPlan,
        result: ActionResult,
    ):
        """Update counters and collect delete ranges for a single chunk."""
        if chunk.action == ActionType.DELETE:
            plan.files_with_deletions.setdefault(doc_file.path, []).append(
                (chunk.line_start, chunk.line_end)
            )
            result.deleted_chunks += 1
        elif chunk.action == ActionType.ARCHIVE:
            result.archived_files += 1
        elif chunk.action == ActionType.FIX:
            result.fixed_chunks += 1
        elif chunk.action == ActionType.FLAG:
            result.flagged_chunks += 1
        else:
            result.skipped += 1

    def _apply_deletions(
        self,
        files_with_deletions: dict[Path, list[tuple[int, int]]],
        result: ActionResult,
    ):
        """Apply file section deletions and record any failures."""
        for filepath, ranges in files_with_deletions.items():
            try:
                self._delete_sections(filepath, ranges)
            except OSError as e:
                result.errors.append(f"Delete failed for {filepath}: {e}")

    def _apply_archives(
        self,
        files_to_archive: list[DocFile],
        base_dir: Path,
        result: ActionResult,
    ):
        """Apply archive operations and record any failures."""
        for doc_file in files_to_archive:
            try:
                self._archive_file(doc_file.path, base_dir)
            except OSError as e:
                result.errors.append(f"Archive failed for {doc_file.path}: {e}")

    def _delete_sections(self, filepath: Path, ranges: list[tuple[int, int]]):
        """Remove line ranges from a file."""
        lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)

        # Sort ranges in reverse order to delete from bottom up
        sorted_ranges = sorted(ranges, key=lambda r: r[0], reverse=True)

        for start, end in sorted_ranges:
            # Convert to 0-indexed
            start_idx = max(0, start - 1)
            end_idx = min(len(lines), end)
            del lines[start_idx:end_idx]

        filepath.write_text("".join(lines), encoding="utf-8")

    def _archive_file(self, filepath: Path, base_dir: Path):
        """Move a file to the archive directory, preserving relative path."""
        rel = filepath.relative_to(base_dir)
        dest = self.archive_dir / rel

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(filepath), str(dest))

    def generate_patch(self, doc_files: list[DocFile]) -> str:
        """Generate a unified diff patch for all pending actions."""
        lines: list[str] = []

        for doc_file in doc_files:
            for chunk in doc_file.chunks:
                if chunk.action == ActionType.DELETE:
                    lines.append(f"# DELETE {chunk.file}:{chunk.line_start}-{chunk.line_end}")
                    lines.append(f"# Section: {chunk.heading}")
                    lines.append(f"# Reason: {chunk.issues[0].message if chunk.issues else 'N/A'}")
                    lines.append("")
                elif chunk.action == ActionType.ARCHIVE:
                    lines.append(f"# ARCHIVE {chunk.file}")
                    lines.append(f"# Reason: {chunk.issues[0].message if chunk.issues else 'N/A'}")
                    lines.append("")
                elif chunk.action == ActionType.FIX:
                    lines.append(f"# FIX NEEDED {chunk.file}:{chunk.line_start}-{chunk.line_end}")
                    lines.append(f"# Section: {chunk.heading}")
                    for issue in chunk.issues:
                        lines.append(f"#   Issue: {issue.message}")
                        if issue.suggestion:
                            lines.append(f"#   Suggestion: {issue.suggestion}")
                    lines.append("")
                elif chunk.action == ActionType.FLAG:
                    lines.append(f"# REVIEW {chunk.file}:{chunk.line_start}-{chunk.line_end}")
                    lines.append(f"# Section: {chunk.heading}")
                    for issue in chunk.issues:
                        lines.append(f"#   {issue.message}")
                    lines.append("")

        return "\n".join(lines)
