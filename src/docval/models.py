"""Core data models for documentation validation."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class ChunkStatus(str, enum.Enum):
    VALID = "valid"
    OUTDATED = "outdated"
    INVALID = "invalid"
    DUPLICATE = "duplicate"
    ORPHANED = "orphaned"       # references non-existent code
    EMPTY = "empty"
    UNCHECKED = "unchecked"


class ActionType(str, enum.Enum):
    KEEP = "keep"
    DELETE = "delete"
    ARCHIVE = "archive"
    FIX = "fix"                 # LLM-assisted rewrite
    FLAG = "flag"               # needs manual review


class Severity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Issue:
    """A single validation issue found in a doc chunk."""
    rule: str
    severity: Severity
    message: str
    suggestion: str = ""


@dataclass
class DocChunk:
    """A semantic chunk extracted from a Markdown file."""
    file: Path
    heading: str                # section heading (empty for preamble)
    heading_level: int          # 0 = preamble, 1-6 = H1-H6
    content: str                # full text of the section
    line_start: int
    line_end: int
    status: ChunkStatus = ChunkStatus.UNCHECKED
    issues: list[Issue] = field(default_factory=list)
    action: ActionType = ActionType.KEEP
    confidence: float = 0.0     # 0.0-1.0
    validator: str = ""         # which validator set the status

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def word_count(self) -> int:
        return len(self.content.split())

    @property
    def relative_path(self) -> str:
        return str(self.file)

    def add_issue(self, rule: str, severity: Severity, message: str, suggestion: str = ""):
        self.issues.append(Issue(rule=rule, severity=severity, message=message, suggestion=suggestion))


@dataclass
class DocFile:
    """Represents a single Markdown file with its chunks."""
    path: Path
    relative_path: str
    chunks: list[DocChunk] = field(default_factory=list)
    total_lines: int = 0

    @property
    def status_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.chunks:
            counts[c.status.value] = counts.get(c.status.value, 0) + 1
        return counts

    @property
    def worst_status(self) -> ChunkStatus:
        priority = [
            ChunkStatus.INVALID, ChunkStatus.ORPHANED, ChunkStatus.OUTDATED,
            ChunkStatus.DUPLICATE, ChunkStatus.EMPTY, ChunkStatus.UNCHECKED,
            ChunkStatus.VALID,
        ]
        statuses = {c.status for c in self.chunks}
        for s in priority:
            if s in statuses:
                return s
        return ChunkStatus.VALID


@dataclass
class ProjectContext:
    """Gathered context about the project for cross-referencing."""
    root: Path
    src_files: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    cli_commands: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    version: str = ""
    recent_commits: list[str] = field(default_factory=list)
    toon_data: dict = field(default_factory=dict)
    dir_tree: str = ""


@dataclass
class ValidationResult:
    """Aggregated result of a validation run."""
    files_scanned: int = 0
    chunks_total: int = 0
    chunks_valid: int = 0
    chunks_invalid: int = 0
    chunks_outdated: int = 0
    chunks_duplicate: int = 0
    chunks_orphaned: int = 0
    chunks_empty: int = 0
    doc_files: list[DocFile] = field(default_factory=list)

    def update_counts(self):
        self.files_scanned = len(self.doc_files)
        self.chunks_total = sum(len(f.chunks) for f in self.doc_files)
        self.chunks_valid = self._count(ChunkStatus.VALID)
        self.chunks_invalid = self._count(ChunkStatus.INVALID)
        self.chunks_outdated = self._count(ChunkStatus.OUTDATED)
        self.chunks_duplicate = self._count(ChunkStatus.DUPLICATE)
        self.chunks_orphaned = self._count(ChunkStatus.ORPHANED)
        self.chunks_empty = self._count(ChunkStatus.EMPTY)

    def _count(self, status: ChunkStatus) -> int:
        return sum(
            1 for f in self.doc_files for c in f.chunks if c.status == status
        )
