"""Integration test for the full pipeline."""

from pathlib import Path

import pytest

from docval.pipeline import scan
from docval.models import ChunkStatus


@pytest.fixture
def project_with_docs(tmp_path):
    """Create a minimal project with docs and source code."""
    # Source code
    src = tmp_path / "mypackage"
    src.mkdir()
    (src / "__init__.py").write_text('"""My package."""\n__version__ = "2.0.0"\n')
    (src / "core.py").write_text(
        'class Engine:\n    """Main engine."""\n    def run(self): pass\n\n'
        'def process(data): pass\n'
    )
    (src / "cli.py").write_text(
        'import click\n\n@click.command()\ndef main(): pass\n'
    )

    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mypackage"\nversion = "2.0.0"\n'
        'dependencies = ["click", "rich"]\n'
    )

    # Documentation
    docs = tmp_path / "docs"
    docs.mkdir()

    (docs / "guide.md").write_text(
        "# User Guide\n\n"
        "Use `Engine` class from `mypackage.core` to process data.\n\n"
        "## Installation\n\n"
        "```bash\npip install mypackage\n```\n\n"
        "## API\n\n"
        "Call `process()` with your data.\n"
    )

    (docs / "outdated.md").write_text(
        "# Old Migration Guide\n\n"
        "DEPRECATED: This document is no longer maintained.\n\n"
        "## v1.0 API\n\n"
        "In version 1.2 the API was completely different.\n"
    )

    (docs / "empty.md").write_text("# Empty Section\n\n")

    archive = docs / "archive"
    archive.mkdir()
    (archive / "legacy.md").write_text(
        "# Legacy Documentation\n\n"
        "This section covers the old deployment workflow that was used before the v2 migration.\n"
    )

    return tmp_path


class TestFullPipeline:
    def test_scans_docs(self, project_with_docs):
        result = scan(
            docs_dir=project_with_docs / "docs",
            project_root=project_with_docs,
        )
        # archive/ is excluded from discovery, so only 3 files scanned
        assert result.files_scanned >= 3
        assert result.chunks_total >= 3

    def test_detects_valid_content(self, project_with_docs):
        result = scan(
            docs_dir=project_with_docs / "docs",
            project_root=project_with_docs,
        )
        valid = [
            c for f in result.doc_files for c in f.chunks
            if c.status == ChunkStatus.VALID
        ]
        assert len(valid) >= 1

    def test_detects_outdated(self, project_with_docs):
        result = scan(
            docs_dir=project_with_docs / "docs",
            project_root=project_with_docs,
        )
        outdated = [
            c for f in result.doc_files for c in f.chunks
            if c.status == ChunkStatus.OUTDATED
        ]
        assert len(outdated) >= 1

    def test_detects_empty(self, project_with_docs):
        result = scan(
            docs_dir=project_with_docs / "docs",
            project_root=project_with_docs,
        )
        empty = [
            c for f in result.doc_files for c in f.chunks
            if c.status == ChunkStatus.EMPTY
        ]
        assert len(empty) >= 1

    def test_excludes_archive_from_scan(self, project_with_docs):
        result = scan(
            docs_dir=project_with_docs / "docs",
            project_root=project_with_docs,
        )
        # archive/ directory is excluded from discovery
        archived = [
            f for f in result.doc_files
            if "archive/" in f.relative_path.lower()
        ]
        assert len(archived) == 0

    def test_detects_archive_path_heuristic(self, tmp_path):
        """Files in archive/ are detected as outdated by the heuristic validator."""
        src = tmp_path / "mypackage"
        src.mkdir()
        (src / "__init__.py").write_text('"""My package."""\n')

        docs = tmp_path / "docs"
        docs.mkdir()
        archive = docs / "archive"
        archive.mkdir()
        (archive / "legacy.md").write_text(
            "# Legacy Documentation\n\nThis covers the old deployment workflow.\n"
        )

        # Manually chunk the archive file to test heuristic detection
        from docval.chunker import chunk_file
        from docval.context import build_context
        from docval.validators.heuristic import HeuristicValidator
        from docval.models import DocFile

        doc = chunk_file(archive / "legacy.md", base_dir=docs)
        doc_file = DocFile(
            path=archive / "legacy.md",
            relative_path="archive/legacy.md",
            chunks=doc.chunks,
            total_lines=doc.total_lines,
        )

        ctx = build_context(tmp_path)
        v = HeuristicValidator(ctx=ctx)
        v.validate([doc_file])

        archived = [c for c in doc_file.chunks if c.status == ChunkStatus.OUTDATED]
        assert len(archived) >= 1

    def test_result_counts(self, project_with_docs):
        result = scan(
            docs_dir=project_with_docs / "docs",
            project_root=project_with_docs,
        )
        result.update_counts()
        assert result.chunks_total == (
            result.chunks_valid + result.chunks_invalid +
            result.chunks_outdated + result.chunks_duplicate +
            result.chunks_orphaned + result.chunks_empty +
            sum(1 for f in result.doc_files for c in f.chunks
                if c.status == ChunkStatus.UNCHECKED)
        )
