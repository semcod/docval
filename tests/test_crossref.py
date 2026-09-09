"""Tests for the cross-reference validator."""

from pathlib import Path

import pytest

from docval.models import ChunkStatus, DocChunk, DocFile, ProjectContext
from docval.validators.crossref import CrossRefValidator


def _make_chunk(content: str, heading: str = "Test") -> DocChunk:
    return DocChunk(
        file=Path("test.md"),
        heading=heading,
        heading_level=2,
        content=content,
        line_start=1,
        line_end=10,
    )


def _make_file(chunks: list[DocChunk]) -> DocFile:
    return DocFile(path=Path("test.md"), relative_path="test.md", chunks=chunks, total_lines=100)


@pytest.fixture
def ctx():
    return ProjectContext(
        root=Path("."),
        src_files=[
            "todocs/__init__.py",
            "todocs/cli.py",
            "todocs/core.py",
            "todocs/analyzers/import_graph.py",
        ],
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

    @pytest.mark.parametrize("prefix", ["", "src/", "src\\"])
    def test_internal_module_must_match_full_path(self, tmp_path, prefix):
        context = ProjectContext(
            root=tmp_path,
            src_files=[prefix + "example/__init__.py", prefix + "example/api/client.py"],
            functions=["deleted"],
        )
        chunk = _make_chunk(
            "```python\nfrom example.deleted import Client\n"
            "from example.api import client\nfrom external.deleted import Client\n```"
        )
        CrossRefValidator(context).validate([_make_file([chunk])])
        issues = [issue for issue in chunk.issues if issue.rule == "broken_import"]
        assert len(issues) == 1
        assert "example.deleted" in issues[0].message

    def test_actual_src_package_keeps_its_import_name(self, tmp_path):
        context = ProjectContext(root=tmp_path, src_files=["src/__init__.py", "src/api.py"])
        chunk = _make_chunk("```python\nfrom src.api import Client\nfrom src.deleted import Client\n```")
        CrossRefValidator(context).validate([_make_file([chunk])])
        issues = [issue for issue in chunk.issues if issue.rule == "broken_import"]
        assert len(issues) == 1
        assert "src.deleted" in issues[0].message


@pytest.mark.parametrize("field", ["classes", "functions", "modules", "cli_commands", "endpoints", "dependencies"])
def test_rescan_uses_changed_symbols_even_with_identical_counts(tmp_path, field):
    before = ProjectContext(root=tmp_path, **{field: ["OldClient", "OldParser"]})
    CrossRefValidator(before)
    after = ProjectContext(root=tmp_path, **{field: ["NewClient", "NewParser"]})
    current = _make_chunk("Use `NewClient` and `NewParser`.")
    stale = _make_chunk("Use `OldClient` and `OldParser`.")
    CrossRefValidator(after).validate([_make_file([current, stale])])
    assert not any(issue.rule == "orphaned_code_ref" for issue in current.issues)
    assert any(issue.rule == "orphaned_code_ref" for issue in stale.issues)


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
