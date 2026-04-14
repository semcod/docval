"""Rule-based heuristic validation — fast, no LLM needed.

Checks for: empty content, outdated version references, broken links,
TODO/FIXME markers, archive paths, duplicate detection, stale dates.
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from ..models import (
    ActionType,
    ChunkStatus,
    DocChunk,
    DocFile,
    ProjectContext,
    Severity,
)


class HeuristicValidator:
    """Apply fast heuristic rules to doc chunks before LLM validation."""

    def __init__(self, ctx: ProjectContext | None = None):
        self.ctx = ctx
        self._seen_chunks: list[tuple[str, DocChunk]] = []

    def validate(self, doc_files: list[DocFile]):
        """Run all heuristic checks across all files."""
        self._seen_chunks.clear()

        for doc_file in doc_files:
            for chunk in doc_file.chunks:
                self._check_empty(chunk)
                self._check_outdated_markers(chunk)
                self._check_broken_internal_links(chunk, doc_file, self.ctx)
                self._check_todo_fixme(chunk)
                self._check_archive_path(chunk, doc_file)
                self._check_stale_versions(chunk)
                self._check_duplicates(chunk)
                self._check_minimal_content(chunk)

                # If no issues found, mark as valid (low confidence — LLM may override)
                if chunk.status == ChunkStatus.UNCHECKED and not chunk.issues:
                    chunk.status = ChunkStatus.VALID
                    chunk.confidence = 0.5
                    chunk.validator = "heuristic"

    def _check_empty(self, chunk: DocChunk):
        """Flag chunks with no meaningful content."""
        stripped = re.sub(r"^#+\s+.*$", "", chunk.content, flags=re.MULTILINE).strip()
        stripped = re.sub(r"^\s*[-*]\s*$", "", stripped, flags=re.MULTILINE).strip()

        if len(stripped) < 20:
            chunk.status = ChunkStatus.EMPTY
            chunk.action = ActionType.DELETE
            chunk.confidence = 0.95
            chunk.validator = "heuristic:empty"
            chunk.add_issue("empty", Severity.WARNING, "Section has no meaningful content")

    def _check_outdated_markers(self, chunk: DocChunk):
        """Detect explicit outdated/deprecated markers."""
        outdated_patterns = [
            (r"\b(DEPRECATED|OBSOLETE|DO NOT USE)\b", "Explicit deprecation marker"),
            (r"(?i)\b(legacy|archived)\s+(version|api|approach|code|module|system)\b", "Legacy reference"),
            (r"(?i)\bthis\s+(document|page|section)\s+is\s+(no longer|outdated|deprecated)", "Self-declared outdated"),
        ]

        for pattern, message in outdated_patterns:
            if re.search(pattern, chunk.content, re.IGNORECASE):
                chunk.status = ChunkStatus.OUTDATED
                chunk.action = ActionType.ARCHIVE
                chunk.confidence = 0.9
                chunk.validator = "heuristic:outdated_marker"
                chunk.add_issue("outdated_marker", Severity.WARNING, message)
                return

    def _check_broken_internal_links(self, chunk: DocChunk, doc_file: DocFile, ctx: ProjectContext | None = None):
        """Check for internal Markdown links pointing to non-existent files."""
        # Strip fenced code blocks to avoid matching Python calls like func(arg)
        content_no_code = re.sub(r"```[\s\S]*?```", "", chunk.content)
        # Also strip inline code
        content_no_code = re.sub(r"`[^`]+`", "", content_no_code)

        link_re = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
        for match in link_re.finditer(content_no_code):
            target = match.group(2)
            # Skip external URLs, anchors, and absolute paths (GitHub Pages style)
            if target.startswith(("http://", "https://", "#", "mailto:", "/")):
                continue

            # Resolve relative path
            target_path = target.split("#")[0]  # strip anchor
            if not target_path:
                continue

            # Try multiple resolution strategies
            candidates = [
                doc_file.path.parent / target_path,
                doc_file.path.parent / (target_path + ".md"),
            ]
            # Also try resolving relative to project root
            if ctx and ctx.root:
                candidates.extend([
                    ctx.root / target_path,
                    ctx.root / (target_path + ".md"),
                ])

            if not any(c.exists() for c in candidates):
                chunk.add_issue(
                    "broken_link",
                    Severity.ERROR,
                    f"Internal link target not found: {target_path}",
                    suggestion=f"Check if '{target_path}' was moved or deleted",
                )
                if chunk.status == ChunkStatus.UNCHECKED:
                    chunk.status = ChunkStatus.INVALID
                    chunk.action = ActionType.FIX
                    chunk.confidence = 0.85
                    chunk.validator = "heuristic:broken_link"

    def _check_todo_fixme(self, chunk: DocChunk):
        """Flag TODO/FIXME/HACK markers."""
        todo_re = re.compile(r"\b(TODO|FIXME|HACK|XXX|TEMP)\b", re.IGNORECASE)
        matches = todo_re.findall(chunk.content)
        if matches:
            chunk.add_issue(
                "todo_marker",
                Severity.INFO,
                f"Contains {len(matches)} TODO/FIXME marker(s)",
            )

    def _check_archive_path(self, chunk: DocChunk, doc_file: DocFile):
        """Files in archive/ directories are likely outdated."""
        rel = doc_file.relative_path.lower()
        if "/archive/" in rel or rel.startswith("archive/") or "/_archive/" in rel or rel.startswith("_archive/"):
            if chunk.status in (ChunkStatus.UNCHECKED, ChunkStatus.VALID, ChunkStatus.EMPTY):
                chunk.status = ChunkStatus.OUTDATED
                chunk.action = ActionType.ARCHIVE
                chunk.confidence = 0.7
                chunk.validator = "heuristic:archive_path"
                chunk.add_issue(
                    "archive_path",
                    Severity.INFO,
                    "File is in an archive directory — likely outdated",
                )

    def _check_stale_versions(self, chunk: DocChunk):
        """Detect references to old version numbers if project version is known."""
        if not self.ctx or not self.ctx.version:
            return

        # Look for version patterns like v1.x, v2.x when project is v3.x
        current_major = re.match(r"(\d+)", self.ctx.version)
        if not current_major:
            return

        major = int(current_major.group(1))
        if major < 2:
            return  # Not enough version history to flag

        # Find references to older major versions
        old_ver_re = re.compile(rf"\bv?({'|'.join(str(i) for i in range(1, major))})\.\d+")
        matches = old_ver_re.findall(chunk.content)
        if matches:
            chunk.add_issue(
                "stale_version",
                Severity.WARNING,
                f"References old version(s): {', '.join(f'v{m}.x' for m in set(matches))} "
                f"(current: v{self.ctx.version})",
            )
            if chunk.status == ChunkStatus.UNCHECKED:
                chunk.status = ChunkStatus.OUTDATED
                chunk.action = ActionType.FLAG
                chunk.confidence = 0.6
                chunk.validator = "heuristic:stale_version"

    def _check_duplicates(self, chunk: DocChunk):
        """Detect near-duplicate content across chunks using SequenceMatcher."""
        # Skip chunks already resolved by earlier checks
        if chunk.status != ChunkStatus.UNCHECKED and chunk.status != ChunkStatus.VALID:
            return
        if chunk.word_count < 30:
            return

        # Normalize content for comparison
        normalized = re.sub(r"\s+", " ", chunk.content.lower().strip())

        for prev_norm, prev_chunk in self._seen_chunks:
            ratio = SequenceMatcher(None, normalized, prev_norm).quick_ratio()
            if ratio > 0.85:
                # Confirm with full ratio
                full_ratio = SequenceMatcher(None, normalized, prev_norm).ratio()
                if full_ratio > 0.80:
                    chunk.status = ChunkStatus.DUPLICATE
                    chunk.action = ActionType.DELETE
                    chunk.confidence = full_ratio
                    chunk.validator = "heuristic:duplicate"
                    chunk.add_issue(
                        "duplicate",
                        Severity.WARNING,
                        f"~{full_ratio:.0%} similar to {prev_chunk.file}:{prev_chunk.line_start}",
                        suggestion=f"Consider removing — duplicate of section '{prev_chunk.heading}'",
                    )
                    break

        self._seen_chunks.append((normalized, chunk))

    def _check_minimal_content(self, chunk: DocChunk):
        """Flag heading-only sections with no meaningful body."""
        lines = chunk.content.strip().splitlines()
        non_heading = [
            l for l in lines
            if not re.match(r"^#+\s+", l) and l.strip()
        ]
        if len(lines) > 0 and len(non_heading) == 0:
            chunk.add_issue(
                "heading_only",
                Severity.INFO,
                "Section contains only a heading with no body text",
            )
