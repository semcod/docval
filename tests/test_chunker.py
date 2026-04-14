"""Tests for the Markdown chunker."""

import tempfile
from pathlib import Path

import pytest

from docval.chunker import chunk_file, chunk_directory, discover_md_files


@pytest.fixture
def sample_md(tmp_path):
    """Create a sample Markdown file."""
    content = """# Main Title

This is the introduction paragraph.

## Getting Started

Install with pip:

```bash
pip install mypackage
```

## API Reference

### Class: MyClass

A useful class that does things.

### Function: helper()

A helper function.

## Changelog

### v2.0.0

Breaking changes.

### v1.0.0

Initial release.
"""
    md_file = tmp_path / "README.md"
    md_file.write_text(content)
    return md_file


@pytest.fixture
def docs_tree(tmp_path):
    """Create a docs directory tree."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n\nSome guide content.\n")
    (tmp_path / "docs" / "api.md").write_text("# API\n\n## Endpoints\n\nGET /health\n")
    (tmp_path / "docs" / "archive").mkdir()
    (tmp_path / "docs" / "archive" / "old.md").write_text("# Old Doc\n\nDeprecated stuff.\n")
    (tmp_path / "docs" / "node_modules").mkdir()
    (tmp_path / "docs" / "node_modules" / "pkg.md").write_text("# Should be excluded\n")
    return tmp_path / "docs"


class TestChunkFile:
    def test_splits_by_headings(self, sample_md, tmp_path):
        doc = chunk_file(sample_md, tmp_path)
        assert len(doc.chunks) >= 5
        headings = [c.heading for c in doc.chunks]
        assert "Main Title" in headings
        assert "Getting Started" in headings
        assert "API Reference" in headings

    def test_heading_levels(self, sample_md, tmp_path):
        doc = chunk_file(sample_md, tmp_path)
        levels = {c.heading: c.heading_level for c in doc.chunks}
        assert levels["Main Title"] == 1
        assert levels["Getting Started"] == 2
        assert levels["Class: MyClass"] == 3

    def test_line_numbers(self, sample_md, tmp_path):
        doc = chunk_file(sample_md, tmp_path)
        for chunk in doc.chunks:
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

    def test_content_preserved(self, sample_md, tmp_path):
        doc = chunk_file(sample_md, tmp_path)
        getting_started = next(c for c in doc.chunks if c.heading == "Getting Started")
        assert "pip install" in getting_started.content

    def test_no_headings(self, tmp_path):
        f = tmp_path / "plain.md"
        f.write_text("Just some text.\nNo headings here.\n")
        doc = chunk_file(f, tmp_path)
        assert len(doc.chunks) == 1
        assert doc.chunks[0].heading == "(no heading)"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        doc = chunk_file(f, tmp_path)
        assert len(doc.chunks) == 0

    def test_preamble_before_first_heading(self, tmp_path):
        f = tmp_path / "preamble.md"
        f.write_text("Some preamble text here.\n\n# Title\n\nBody.\n")
        doc = chunk_file(f, tmp_path)
        assert doc.chunks[0].heading == "(preamble)"
        assert doc.chunks[0].heading_level == 0


class TestDiscoverFiles:
    def test_finds_md_files(self, docs_tree):
        files = discover_md_files(docs_tree)
        names = {f.name for f in files}
        assert "guide.md" in names
        assert "api.md" in names

    def test_excludes_archive(self, docs_tree):
        files = discover_md_files(docs_tree)
        paths = {str(f.relative_to(docs_tree)) for f in files}
        assert not any("archive" in p for p in paths)

    def test_excludes_node_modules(self, docs_tree):
        files = discover_md_files(docs_tree)
        rel_paths = [str(f.relative_to(docs_tree)) for f in files]
        assert not any("node_modules" in p for p in rel_paths)

    def test_custom_excludes(self, docs_tree):
        files = discover_md_files(docs_tree, exclude_patterns=["extra_dir"])
        assert not any("extra_dir" in str(f) for f in files)


class TestChunkDirectory:
    def test_chunks_all_files(self, docs_tree):
        doc_files = chunk_directory(docs_tree)
        assert len(doc_files) >= 2
        total_chunks = sum(len(f.chunks) for f in doc_files)
        assert total_chunks >= 3
