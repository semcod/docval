"""Tests for the heuristic validator."""

from pathlib import Path

import pytest

from docval.models import ActionType, ChunkStatus, DocChunk, DocFile, ProjectContext
from docval.validators.heuristic import HeuristicValidator


def _make_chunk(content: str, heading: str = "Test", file_name: str = "test.md", line_start: int = 1) -> DocChunk:
    return DocChunk(
        file=Path(file_name),
        heading=heading,
        heading_level=2,
        content=content,
        line_start=line_start,
        line_end=line_start + content.count("\n"),
    )


def _make_file(chunks: list[DocChunk], path: str = "test.md") -> DocFile:
    return DocFile(path=Path(path), relative_path=path, chunks=chunks, total_lines=100)


class TestEmptyCheck:
    def test_flags_empty_content(self):
        chunk = _make_chunk("## Heading\n\n")
        v = HeuristicValidator()
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.EMPTY

    def test_keeps_real_content(self):
        chunk = _make_chunk("## API\n\nThis module provides HTTP endpoints for managing users.")
        v = HeuristicValidator()
        v.validate([_make_file([chunk])])
        assert chunk.status != ChunkStatus.EMPTY


class TestOutdatedMarkers:
    def test_detects_deprecated(self):
        chunk = _make_chunk("## Old API\n\nDEPRECATED: Use new API instead.")
        v = HeuristicValidator()
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.OUTDATED

    def test_detects_self_declared_outdated(self):
        chunk = _make_chunk("This document is no longer maintained.")
        v = HeuristicValidator()
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.OUTDATED


class TestArchivePath:
    def test_flags_archive_directory(self):
        chunk = _make_chunk(
            "This section describes the old deployment process that was used before the migration.",
            file_name="docs/archive/old-guide.md",
        )
        doc = _make_file([chunk], path="docs/archive/old-guide.md")
        v = HeuristicValidator()
        v.validate([doc])
        assert chunk.status == ChunkStatus.OUTDATED
        assert chunk.action == ActionType.ARCHIVE


class TestStaleVersions:
    def test_detects_old_version_refs(self):
        ctx = ProjectContext(root=Path("."), version="3.0.27")
        chunk = _make_chunk("## Migration from v1.x\n\nIn version 1.5 the API was different.")
        v = HeuristicValidator(ctx=ctx)
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.OUTDATED
        assert any("old version" in i.message.lower() or "stale" in i.rule for i in chunk.issues)

    def test_ignores_current_version(self):
        ctx = ProjectContext(root=Path("."), version="3.0.27")
        chunk = _make_chunk("## What's new in v3.0\n\nNew features in the current release.")
        v = HeuristicValidator(ctx=ctx)
        v.validate([_make_file([chunk])])
        assert chunk.status != ChunkStatus.OUTDATED


class TestDuplicateDetection:
    def test_detects_near_duplicates(self):
        content = (
            "This is a detailed guide about installing the package and configuring "
            "the environment variables for local development. You need to set up "
            "Python 3.10 or later and install all required dependencies before running "
            "the application server for the first time."
        )
        chunk1 = _make_chunk(content, heading="Install Guide", file_name="guide1.md")
        chunk2 = _make_chunk(
            content + " Also remember to set PATH correctly.",
            heading="Installation", file_name="guide2.md"
        )
        v = HeuristicValidator()
        v.validate([_make_file([chunk1], "guide1.md"), _make_file([chunk2], "guide2.md")])
        assert chunk2.status == ChunkStatus.DUPLICATE

    def test_different_content_not_duplicate(self):
        chunk1 = _make_chunk("Guide about installing Python packages on Linux systems.", heading="Install")
        chunk2 = _make_chunk("Reference for the REST API endpoints and authentication.", heading="API")
        v = HeuristicValidator()
        v.validate([_make_file([chunk1]), _make_file([chunk2])])
        assert chunk2.status != ChunkStatus.DUPLICATE


class TestTodoFixme:
    def test_flags_todo(self):
        chunk = _make_chunk("## Setup\n\nTODO: Add more examples here.")
        v = HeuristicValidator()
        v.validate([_make_file([chunk])])
        assert any(i.rule == "todo_marker" for i in chunk.issues)


class TestBrokenLinks:
    def test_flags_broken_internal_link(self, tmp_path):
        md = tmp_path / "readme.md"
        md.write_text("See [guide](./nonexistent.md) for details.")
        chunk = _make_chunk("See [guide](./nonexistent.md) for details.", file_name=str(md))
        chunk.file = md
        doc = _make_file([chunk], str(md))
        doc.path = md

        v = HeuristicValidator()
        v.validate([doc])
        assert any(i.rule == "broken_link" for i in chunk.issues)

    def test_ignores_external_links(self, tmp_path):
        md = tmp_path / "readme.md"
        md.write_text("See [docs](https://example.com) for more.")
        chunk = _make_chunk("See [docs](https://example.com) for more.", file_name=str(md))
        chunk.file = md
        doc = _make_file([chunk], str(md))
        doc.path = md

        v = HeuristicValidator()
        v.validate([doc])
        assert not any(i.rule == "broken_link" for i in chunk.issues)

    def test_resolves_md_extension(self, tmp_path):
        """Links like [API](./api) should resolve to ./api.md."""
        md = tmp_path / "readme.md"
        md.write_text("text")
        (tmp_path / "api.md").write_text("API docs")
        chunk = _make_chunk("See [API](./api) for details.", file_name=str(md))
        chunk.file = md
        doc = _make_file([chunk], str(md))
        doc.path = md

        v = HeuristicValidator()
        v.validate([doc])
        assert not any(i.rule == "broken_link" for i in chunk.issues)

    def test_resolves_relative_to_project_root(self, tmp_path):
        """Links like ./LICENSE in docs/README.md should resolve from project root."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        md = docs_dir / "README.md"
        md.write_text("text")
        (tmp_path / "LICENSE").write_text("MIT")
        chunk = _make_chunk("See [License](./LICENSE).", file_name=str(md))
        chunk.file = md
        doc = _make_file([chunk], str(md))
        doc.path = md

        ctx = ProjectContext(root=tmp_path)
        v = HeuristicValidator(ctx=ctx)
        v.validate([doc])
        assert not any(i.rule == "broken_link" for i in chunk.issues)


class TestArchivePathExtended:
    def test_flags_underscore_archive_directory(self):
        chunk = _make_chunk(
            "This section describes the old deployment process.",
            file_name="docs/_archive/old-guide.md",
        )
        doc = _make_file([chunk], path="docs/_archive/old-guide.md")
        v = HeuristicValidator()
        v.validate([doc])
        assert chunk.status == ChunkStatus.OUTDATED


class TestOutdatedMarkersNarrow:
    def test_does_not_flag_old_version_in_normal_text(self):
        """'old version' in normal descriptive text should not be flagged."""
        chunk = _make_chunk("This replaces the old version with a new implementation.")
        v = HeuristicValidator()
        v.validate([_make_file([chunk])])
        assert chunk.status != ChunkStatus.OUTDATED

    def test_flags_legacy_api(self):
        chunk = _make_chunk("This is the legacy API and should not be used.")
        v = HeuristicValidator()
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.OUTDATED
