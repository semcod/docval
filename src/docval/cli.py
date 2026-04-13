"""CLI interface for docval — documentation validation and refactoring."""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
@click.version_option(package_name="docval")
def main():
    """Validate and refactor Markdown documentation against source code."""


@main.command()
@click.argument("docs_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--project", "-p", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=None, help="Project root (default: parent of docs_dir)")
@click.option("--exclude", "-e", multiple=True, help="Directory names to exclude")
@click.option("--llm/--no-llm", default=False, help="Use LLM for semantic validation")
@click.option("--model", "-m", default="gpt-4o-mini", help="LiteLLM model identifier")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output report file (.md or .json)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def scan(
    docs_dir: Path,
    project: Path | None,
    exclude: tuple[str, ...],
    llm: bool,
    model: str,
    output: Path | None,
    verbose: bool,
):
    """Scan documentation and report issues.

    DOCS_DIR is the path to the documentation directory to validate.

    Examples:

        docval scan docs/

        docval scan docs/ --project /path/to/repo --llm --model gpt-4o

        docval scan docs/ -o report.json -v
    """
    from .pipeline import scan as run_scan
    from .reporters import ConsoleReporter, MarkdownReporter, JSONReporter

    result = run_scan(
        docs_dir=docs_dir,
        project_root=project,
        exclude=list(exclude),
        use_llm=llm,
        llm_model=model,
        verbose=verbose,
    )

    # Console report (always)
    console_reporter = ConsoleReporter(verbose=verbose)
    console_reporter.report(result)

    # File report (if requested)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix == ".json":
            JSONReporter().report(result, output)
        else:
            MarkdownReporter().report(result, output)
        click.echo(f"\nReport written to {output}")


@main.command()
@click.argument("docs_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--project", "-p", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=None, help="Project root")
@click.option("--exclude", "-e", multiple=True, help="Directory names to exclude")
@click.option("--force", is_flag=True, help="Apply changes without confirmation")
@click.option("--archive-dir", type=click.Path(path_type=Path),
              default=None, help="Directory for archived docs")
@click.option("--dry-run/--no-dry-run", default=True,
              help="Preview changes without applying (default: dry-run)")
@click.option("--llm/--no-llm", default=False, help="Use LLM for semantic validation")
@click.option("--model", "-m", default="gpt-4o-mini", help="LiteLLM model identifier")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def fix(
    docs_dir: Path,
    project: Path | None,
    exclude: tuple[str, ...],
    force: bool,
    archive_dir: Path | None,
    dry_run: bool,
    llm: bool,
    model: str,
    verbose: bool,
):
    """Validate and apply fixes to documentation.

    By default runs in dry-run mode. Use --no-dry-run to apply changes.

    Examples:

        docval fix docs/                           # dry-run preview

        docval fix docs/ --no-dry-run              # apply fixes

        docval fix docs/ --no-dry-run --llm        # with LLM validation
    """
    from .pipeline import scan as run_scan
    from .actions import ActionExecutor
    from .reporters import ConsoleReporter

    result = run_scan(
        docs_dir=docs_dir,
        project_root=project,
        exclude=list(exclude),
        use_llm=llm,
        llm_model=model,
        verbose=verbose,
    )

    # Show report
    ConsoleReporter(verbose=verbose).report(result)

    # Generate action plan
    executor = ActionExecutor(archive_dir=archive_dir, dry_run=dry_run)

    if dry_run:
        click.echo("\n--- DRY RUN (no changes applied) ---")
        patch = executor.generate_patch(result.doc_files)
        if patch.strip():
            click.echo(patch)
        else:
            click.echo("No actions to apply.")
        click.echo("\nUse --no-dry-run to apply changes.")
        return

    if not force:
        from .models import ActionType
        action_counts = {}
        for f in result.doc_files:
            for c in f.chunks:
                if c.action != ActionType.KEEP:
                    action_counts[c.action.value] = action_counts.get(c.action.value, 0) + 1

        if not action_counts:
            click.echo("\nNo actions to apply — all documentation looks good.")
            return

        click.echo("\nPending actions:")
        for action, count in action_counts.items():
            click.echo(f"  {action}: {count}")

        if not click.confirm("\nApply these changes?"):
            click.echo("Aborted.")
            return

    action_result = executor.execute(result.doc_files, docs_dir)
    click.echo(f"\nActions applied:")
    click.echo(f"  Deleted sections: {action_result.deleted_chunks}")
    click.echo(f"  Archived files:   {action_result.archived_files}")
    click.echo(f"  Flagged for fix:  {action_result.fixed_chunks}")
    click.echo(f"  Flagged review:   {action_result.flagged_chunks}")
    if action_result.errors:
        click.echo(f"\nErrors:")
        for err in action_result.errors:
            click.echo(f"  {err}")


@main.command()
@click.argument("docs_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--project", "-p", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=None, help="Project root")
@click.option("--exclude", "-e", multiple=True, help="Directory names to exclude")
@click.option("--output", "-o", type=click.Path(path_type=Path),
              default=Path("docval-patch.txt"), help="Output patch file")
@click.option("--llm/--no-llm", default=False, help="Use LLM for semantic validation")
@click.option("--model", "-m", default="gpt-4o-mini", help="LiteLLM model identifier")
def patch(
    docs_dir: Path,
    project: Path | None,
    exclude: tuple[str, ...],
    output: Path,
    llm: bool,
    model: str,
):
    """Generate a patch file with recommended changes.

    Examples:

        docval patch docs/ -o fixes.txt

        docval patch docs/ --llm -o fixes.txt
    """
    from .pipeline import scan as run_scan
    from .actions import ActionExecutor

    result = run_scan(
        docs_dir=docs_dir,
        project_root=project,
        exclude=list(exclude),
        use_llm=llm,
        llm_model=model,
        verbose=False,
    )

    executor = ActionExecutor(dry_run=True)
    patch_text = executor.generate_patch(result.doc_files)

    if patch_text.strip():
        output.write_text(patch_text, encoding="utf-8")
        click.echo(f"Patch written to {output}")
    else:
        click.echo("No issues found — no patch needed.")


@main.command()
@click.argument("docs_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--exclude", "-e", multiple=True, help="Directory names to exclude")
def stats(docs_dir: Path, exclude: tuple[str, ...]):
    """Show documentation statistics (no validation).

    Examples:

        docval stats docs/
    """
    from .chunker import chunk_directory

    doc_files = chunk_directory(docs_dir, exclude_patterns=list(exclude))
    total_files = len(doc_files)
    total_chunks = sum(len(f.chunks) for f in doc_files)
    total_lines = sum(f.total_lines for f in doc_files)
    total_words = sum(c.word_count for f in doc_files for c in f.chunks)

    # Heading level distribution
    level_counts: dict[int, int] = {}
    for f in doc_files:
        for c in f.chunks:
            level_counts[c.heading_level] = level_counts.get(c.heading_level, 0) + 1

    click.echo(f"Documentation statistics for {docs_dir}")
    click.echo(f"  Files:    {total_files}")
    click.echo(f"  Sections: {total_chunks}")
    click.echo(f"  Lines:    {total_lines:,}")
    click.echo(f"  Words:    {total_words:,}")
    click.echo()
    click.echo("  Sections by heading level:")
    for level in sorted(level_counts):
        label = f"H{level}" if level > 0 else "preamble"
        click.echo(f"    {label}: {level_counts[level]}")

    # Largest files
    by_size = sorted(doc_files, key=lambda f: f.total_lines, reverse=True)[:10]
    click.echo()
    click.echo("  Largest files:")
    for f in by_size:
        click.echo(f"    {f.total_lines:>5}L  {f.relative_path}")


if __name__ == "__main__":
    main()
