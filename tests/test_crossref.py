"""Tests for the cross-reference validator."""

from pathlib import Path

import pytest

from docval.models import ChunkStatus, DocChunk, DocFile, ProjectContext
from docval.validators.crossref import CrossRefValidator


def _make_chunk(content: str, heading: str = "Test") -> DocChunk:
    return DocChunk(
        file=Path("test.md"), heading=heading, heading_level=2,
        content=content, line_start=1, line_end=10,
    )


def _make_file(chunks: list[DocChunk]) -> DocFile:
    return DocFile(path=Path("test.md"), relative_path="test.md", chunks=chunks, total_lines=100)


@pytest.fixture
def ctx():
    return ProjectContext(
        root=Path("."),
        src_files=["todocs/__init__.py", "todocs/cli.py", "todocs/core.py",
                    "todocs/analyzers/import_graph.py"],
        classes=["ArticleGenerator", "ComparisonGenerator", "ToonParser"],
        functions=["scan_project", "generate_articles", "main"],
        modules=["todocs.cli", "todocs.core", "todocs.analyzers.import_graph"],
        cli_commands=["generate", "inspect", "compare"],
        dependencies=["click", "rich", "radon"],
    )


class TestCodeReferences:
    def test_valid_references_pass(self, ctx):
        chunk = _make_chunk("Use `ArticleGenerator` to generate articles via `scan_project`.")
        v = CrossRefValidator(ctx)
        v.validate([_make_file([chunk])])
        assert chunk.status != ChunkStatus.ORPHANED

    def test_orphaned_references_flagged(self, ctx):
        chunk = _make_chunk(
            "Use `NonExistentClass` and `fake_function` and `BogusAnalyzer` to do things."
        )
        v = CrossRefValidator(ctx)
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.ORPHANED

    def test_short_refs_ignored(self, ctx):
        chunk = _make_chunk("Set `x` to `y` and use `FakeModule` reference.")
        v = CrossRefValidator(ctx)
        v.validate([_make_file([chunk])])
        # Only 1 unknown ref (FakeModule), threshold is 2
        assert chunk.status != ChunkStatus.ORPHANED


class TestImportPaths:
    def test_valid_import(self, ctx):
        chunk = _make_chunk("```python\nfrom todocs.core import scan_project\n```")
        v = CrossRefValidator(ctx)
        v.validate([_make_file([chunk])])
        assert not any(i.rule == "broken_import" for i in chunk.issues)

    def test_broken_import(self, ctx):
        chunk = _make_chunk("```python\nfrom todocs.nonexistent import something\n```")
        v = CrossRefValidator(ctx)
        v.validate([_make_file([chunk])])
        assert any(i.rule == "broken_import" for i in chunk.issues)


class TestSkipsResolvedChunks:
    def test_skips_empty(self, ctx):
        chunk = _make_chunk("")
        chunk.status = ChunkStatus.EMPTY
        v = CrossRefValidator(ctx)
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.EMPTY  # unchanged

    def test_skips_duplicate(self, ctx):
        chunk = _make_chunk("Some content with `FakeClass`")
        chunk.status = ChunkStatus.DUPLICATE
        v = CrossRefValidator(ctx)
        v.validate([_make_file([chunk])])
        assert chunk.status == ChunkStatus.DUPLICATE  # unchanged
