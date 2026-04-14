"""CLI interface for docval — documentation validation and refactoring."""

from __future__ import annotations

from pathlib import Path

import click

from .models import ActionType


def _resolve_project_paths(docs_dir: Path, project: Path | None) -> tuple[Path, Path]:
    docs_dir = docs_dir.resolve()
    project = (project or docs_dir.parent).resolve()
    return docs_dir, project


def _run_scan(
    docs_dir: Path,
    project: Path,
    exclude: tuple[str, ...],
    llm: bool,
    model: str,
    verbose: bool,
):
    from .pipeline import scan as run_scan

    return run_scan(
        docs_dir=docs_dir,
        project_root=project,
        exclude=list(exclude),
        use_llm=llm,
        llm_model=model,
        verbose=verbose,
    )


def _summarize_actions(result):
    action_counts: dict[str, int] = {}
    for doc_file in result.doc_files:
        for chunk in doc_file.chunks:
            if chunk.action != ActionType.KEEP:
                action_counts[chunk.action.value] = action_counts.get(chunk.action.value, 0) + 1
    return action_counts


def _print_action_counts(action_counts: dict[str, int]):
    if not action_counts:
        click.echo("\nNo actions to apply — all documentation looks good.")
        return False

    click.echo("\nPending actions:")
    for action, count in action_counts.items():
        click.echo(f"  {action}: {count}")
    return True


def _export_todo(result, project: Path):
    from .exporters import TodoExporter

    todo_path = project / "TODO.md"
    TodoExporter().export(result, output_path=todo_path)
    click.echo(f"  ✓ Exported to {todo_path}")


def _export_planfile(
    result,
    project: Path,
    github_owner: str | None,
    github_repo: str | None,
    sprint_id: str,
):
    from .exporters import PlanfileExporter

    planfile_path = project / "planfile.yaml"
    exporter = PlanfileExporter(
        project_name=project.name,
        github_owner=github_owner,
        github_repo=github_repo,
    )
    exporter.export(result, output_path=planfile_path, sprint_id=sprint_id)
    click.echo(f"  ✓ Exported to {planfile_path}")


def _export_github(
    result,
    github_owner: str,
    github_repo: str,
    github_token: str | None,
    dry_run: bool,
):
    from .exporters import GitHubExporter

    if dry_run:
        click.echo(f"\n[DRY RUN] Would export to GitHub: {github_owner}/{github_repo}")
    else:
        click.echo(f"\nExporting to GitHub: {github_owner}/{github_repo}...")

    exporter = GitHubExporter(
        owner=github_owner,
        repo=github_repo,
        token=github_token,
        dry_run=dry_run,
    )
    results = exporter.export(result)

    created = sum(1 for r in results if r.get("status") == "created")
    updated = sum(1 for r in results if r.get("status") == "updated")
    failed = sum(1 for r in results if r.get("status") == "failed")

    if dry_run:
        click.echo(f"  Would create {len(results)} issues")
    else:
        click.echo(f"  Created: {created}, Updated: {updated}, Failed: {failed}")


def _export_gitlab(
    result,
    gitlab_project: str,
    gitlab_token: str | None,
    gitlab_url: str,
    dry_run: bool,
):
    from .exporters import GitLabExporter

    if dry_run:
        click.echo(f"\n[DRY RUN] Would export to GitLab project: {gitlab_project}")
    else:
        click.echo(f"\nExporting to GitLab project: {gitlab_project}...")

    exporter = GitLabExporter(
        project_id=gitlab_project,
        token=gitlab_token,
        url=gitlab_url,
        dry_run=dry_run,
    )
    results = exporter.export(result)

    created = sum(1 for r in results if r.get("status") == "created")
    failed = sum(1 for r in results if r.get("status") == "failed")

    if dry_run:
        click.echo(f"  Would create {len(results)} issues")
    else:
        click.echo(f"  Created: {created}, Failed: {failed}")


def _print_sync_planfile_help():
    click.echo("\nNo export destination specified. Use one of:")
    click.echo("  --export-yaml       Export to planfile.yaml")
    click.echo("  --export-todo       Export to TODO.md")
    click.echo("  --github-owner      Export to GitHub Issues")
    click.echo("  --gitlab-project    Export to GitLab Issues")
    click.echo("\nExample:")
    click.echo("  docval sync-planfile docs/ --export-yaml --export-todo")


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
    from .reporters import ConsoleReporter, MarkdownReporter, JSONReporter

    docs_dir, project = _resolve_project_paths(docs_dir, project)
    result = _run_scan(docs_dir, project, exclude, llm, model, verbose)

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
    from .actions import ActionExecutor
    from .reporters import ConsoleReporter

    docs_dir, project = _resolve_project_paths(docs_dir, project)
    result = _run_scan(docs_dir, project, exclude, llm, model, verbose)

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
        action_counts = _summarize_actions(result)
        if not _print_action_counts(action_counts):
            return

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
    from .actions import ActionExecutor

    docs_dir, project = _resolve_project_paths(docs_dir, project)
    result = _run_scan(docs_dir, project, exclude, llm, model, False)

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


@main.command("sync-planfile")
@click.argument("docs_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--project", "-p", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=None, help="Project root (default: parent of docs_dir)")
@click.option("--exclude", "-e", multiple=True, help="Directory names to exclude")
@click.option("--export-yaml", is_flag=True, help="Export to planfile.yaml")
@click.option("--export-todo", is_flag=True, help="Export to TODO.md")
@click.option("--github-owner", help="GitHub owner/organization")
@click.option("--github-repo", help="GitHub repository name")
@click.option("--github-token", help="GitHub token (or set GITHUB_TOKEN env var)")
@click.option("--gitlab-project", help="GitLab project ID")
@click.option("--gitlab-token", help="GitLab token (or set GITLAB_TOKEN env var)")
@click.option("--gitlab-url", default="https://gitlab.com", help="GitLab instance URL")
@click.option("--dry-run/--no-dry-run", default=True,
              help="Preview changes without applying (default: dry-run)")
@click.option("--sprint-id", default="doc-cleanup", help="Sprint identifier")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def sync_planfile(
    docs_dir: Path,
    project: Path | None,
    exclude: tuple[str, ...],
    export_yaml: bool,
    export_todo: bool,
    github_owner: str | None,
    github_repo: str | None,
    github_token: str | None,
    gitlab_project: str | None,
    gitlab_token: str | None,
    gitlab_url: str,
    dry_run: bool,
    sprint_id: str,
    verbose: bool,
):
    """Sync docval results to planfile, GitHub, or GitLab.

    By default runs in dry-run mode. Use --no-dry-run to apply changes.

    Examples:

        docval sync-planfile docs/ --export-yaml --export-todo

        docval sync-planfile docs/ --github-owner wronai --github-repo docval --no-dry-run

        docval sync-planfile docs/ --gitlab-project 12345 --no-dry-run
    """
    docs_dir, project = _resolve_project_paths(docs_dir, project)

    if verbose:
        click.echo(f"Scanning documentation in {docs_dir}...")

    result = _run_scan(docs_dir, project, exclude, False, "gpt-4o-mini", verbose)

    click.echo(f"Found {len(result.doc_files)} files with issues to export")

    exported = False
    if export_todo:
        _export_todo(result, project)
        exported = True

    if export_yaml:
        _export_planfile(result, project, github_owner, github_repo, sprint_id)
        exported = True

    if github_owner and github_repo:
        _export_github(result, github_owner, github_repo, github_token, dry_run)
        exported = True

    if gitlab_project:
        _export_gitlab(result, gitlab_project, gitlab_token, gitlab_url, dry_run)
        exported = True

    if not exported:
        _print_sync_planfile_help()


if __name__ == "__main__":
    main()
