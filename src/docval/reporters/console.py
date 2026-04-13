"""Rich console reporter for docval results."""

from __future__ import annotations

from ..models import ActionType, ChunkStatus, DocFile, Severity, ValidationResult

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


_STATUS_COLORS = {
    ChunkStatus.VALID: "green",
    ChunkStatus.OUTDATED: "yellow",
    ChunkStatus.INVALID: "red",
    ChunkStatus.DUPLICATE: "magenta",
    ChunkStatus.ORPHANED: "cyan",
    ChunkStatus.EMPTY: "dim",
    ChunkStatus.UNCHECKED: "white",
}

_ACTION_COLORS = {
    ActionType.KEEP: "green",
    ActionType.DELETE: "red",
    ActionType.ARCHIVE: "yellow",
    ActionType.FIX: "blue",
    ActionType.FLAG: "magenta",
}


class ConsoleReporter:
    """Print validation results to the console using rich."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.console = Console() if HAS_RICH else None

    def report(self, result: ValidationResult):
        """Print full validation report."""
        result.update_counts()

        if not HAS_RICH:
            self._report_plain(result)
            return

        self._print_summary(result)
        self._print_issues_table(result)

        if self.verbose:
            self._print_details(result)

    def _print_summary(self, result: ValidationResult):
        total = result.chunks_total
        if total == 0:
            self.console.print("[yellow]No documentation chunks found.[/yellow]")
            return

        valid_pct = result.chunks_valid / total * 100 if total else 0
        color = "green" if valid_pct > 80 else "yellow" if valid_pct > 50 else "red"

        summary = (
            f"[bold]Files scanned:[/bold] {result.files_scanned}\n"
            f"[bold]Total chunks:[/bold]  {total}\n"
            f"\n"
            f"[green]  Valid:[/green]     {result.chunks_valid:>4}\n"
            f"[yellow]  Outdated:[/yellow]  {result.chunks_outdated:>4}\n"
            f"[red]  Invalid:[/red]   {result.chunks_invalid:>4}\n"
            f"[magenta]  Duplicate:[/magenta] {result.chunks_duplicate:>4}\n"
            f"[cyan]  Orphaned:[/cyan]  {result.chunks_orphaned:>4}\n"
            f"[dim]  Empty:[/dim]     {result.chunks_empty:>4}\n"
            f"\n"
            f"[bold {color}]Health: {valid_pct:.0f}% valid[/bold {color}]"
        )

        self.console.print(Panel(summary, title="docval results", border_style=color))

    def _print_issues_table(self, result: ValidationResult):
        table = Table(title="Issues found", show_lines=False, expand=True)
        table.add_column("File", style="cyan", ratio=3)
        table.add_column("Section", ratio=2)
        table.add_column("Status", justify="center", ratio=1)
        table.add_column("Action", justify="center", ratio=1)
        table.add_column("Issue", ratio=4)

        count = 0
        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if chunk.status == ChunkStatus.VALID and not self.verbose:
                    continue

                status_color = _STATUS_COLORS.get(chunk.status, "white")
                action_color = _ACTION_COLORS.get(chunk.action, "white")

                issue_text = ""
                if chunk.issues:
                    issue_text = chunk.issues[0].message[:60]
                    if len(chunk.issues) > 1:
                        issue_text += f" (+{len(chunk.issues) - 1})"

                table.add_row(
                    f"{doc_file.relative_path}:{chunk.line_start}",
                    chunk.heading[:30],
                    f"[{status_color}]{chunk.status.value}[/{status_color}]",
                    f"[{action_color}]{chunk.action.value}[/{action_color}]",
                    issue_text,
                )
                count += 1

                if count >= 50 and not self.verbose:
                    table.add_row("...", "...", "...", "...", f"({count} more)")
                    break

        if count > 0:
            self.console.print(table)

    def _print_details(self, result: ValidationResult):
        """Print detailed per-chunk information."""
        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if not chunk.issues:
                    continue

                self.console.print(
                    f"\n[bold]{doc_file.relative_path}[/bold]"
                    f":{chunk.line_start}-{chunk.line_end} "
                    f"[dim]({chunk.heading})[/dim]"
                )

                for issue in chunk.issues:
                    sev_color = {
                        Severity.INFO: "blue",
                        Severity.WARNING: "yellow",
                        Severity.ERROR: "red",
                        Severity.CRITICAL: "bold red",
                    }.get(issue.severity, "white")

                    self.console.print(
                        f"  [{sev_color}]{issue.severity.value}[/{sev_color}] "
                        f"{issue.rule}: {issue.message}"
                    )
                    if issue.suggestion:
                        self.console.print(f"  [dim]→ {issue.suggestion}[/dim]")

    def _report_plain(self, result: ValidationResult):
        """Fallback plain text report when rich is not available."""
        print(f"docval results: {result.files_scanned} files, {result.chunks_total} chunks")
        print(f"  Valid: {result.chunks_valid}")
        print(f"  Outdated: {result.chunks_outdated}")
        print(f"  Invalid: {result.chunks_invalid}")
        print(f"  Duplicate: {result.chunks_duplicate}")
        print(f"  Orphaned: {result.chunks_orphaned}")
        print(f"  Empty: {result.chunks_empty}")

        for doc_file in result.doc_files:
            for chunk in doc_file.chunks:
                if chunk.status != ChunkStatus.VALID:
                    print(
                        f"  {doc_file.relative_path}:{chunk.line_start} "
                        f"[{chunk.status.value}] {chunk.action.value} "
                        f"- {chunk.issues[0].message if chunk.issues else ''}"
                    )
