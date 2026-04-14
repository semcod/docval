"""Split Markdown files into semantic chunks by heading structure."""

from __future__ import annotations

import re
from pathlib import Path

from .models import DocChunk, DocFile


# Matches ATX headings: # Title, ## Title, etc.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def chunk_file(path: Path, base_dir: Path | None = None) -> DocFile:
    """Parse a single Markdown file into heading-based chunks.

    Each chunk corresponds to one heading section (from the heading line
    to the line before the next heading of equal or higher level).
    Content before the first heading becomes a "preamble" chunk.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return DocFile(path=path, relative_path=str(path), chunks=[], total_lines=0)

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)
    rel = str(path.relative_to(base_dir)) if base_dir else str(path)

    # Find all heading positions
    headings: list[tuple[int, int, str]] = []  # (line_idx, level, title)
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line.rstrip())
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((i, level, title))

    chunks: list[DocChunk] = []

    if not headings:
        # No headings — entire file is one chunk
        content = text.strip()
        if content:
            chunks.append(DocChunk(
                file=path,
                heading="(no heading)",
                heading_level=0,
                content=content,
                line_start=1,
                line_end=total_lines,
            ))
        return DocFile(path=path, relative_path=rel, chunks=chunks, total_lines=total_lines)

    # Preamble: content before first heading
    if headings[0][0] > 0:
        preamble = "".join(lines[:headings[0][0]]).strip()
        if preamble:
            chunks.append(DocChunk(
                file=path,
                heading="(preamble)",
                heading_level=0,
                content=preamble,
                line_start=1,
                line_end=headings[0][0],
            ))

    # Each heading section
    for idx, (line_idx, level, title) in enumerate(headings):
        if idx + 1 < len(headings):
            end_idx = headings[idx + 1][0]
        else:
            end_idx = total_lines

        content = "".join(lines[line_idx:end_idx]).strip()
        if content:
            chunks.append(DocChunk(
                file=path,
                heading=title,
                heading_level=level,
                content=content,
                line_start=line_idx + 1,
                line_end=end_idx,
            ))

    return DocFile(path=path, relative_path=rel, chunks=chunks, total_lines=total_lines)


def discover_md_files(
    docs_dir: Path,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    """Recursively find all .md files, excluding node_modules, .git, etc."""
    default_excludes = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".tox", "_archive", "archive"}
    excludes = default_excludes | set(exclude_patterns or [])

    result: list[Path] = []
    for p in sorted(docs_dir.rglob("*.md")):
        rel_parts = p.relative_to(docs_dir).parts
        # Check if any path component matches excludes or is hidden
        if any(part in excludes or part.startswith(".") for part in rel_parts):
            continue
        result.append(p)
    return result


def chunk_directory(docs_dir: Path, exclude_patterns: list[str] | None = None) -> list[DocFile]:
    """Chunk all Markdown files in a directory."""
    files = discover_md_files(docs_dir, exclude_patterns)
    return [chunk_file(f, base_dir=docs_dir) for f in files]
