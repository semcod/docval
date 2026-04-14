"""Cross-reference validator — checks that docs reference real code entities.

Verifies: class names, function names, module paths, CLI commands,
API endpoints mentioned in docs exist in the project source.
"""

from __future__ import annotations

import re

from ..models import (
    ActionType,
    ChunkStatus,
    DocChunk,
    DocFile,
    ProjectContext,
    Severity,
)


class CrossRefValidator:
    """Validate documentation references against actual project code."""

    def __init__(self, ctx: ProjectContext):
        self.ctx = ctx
        self._known_symbols = self._build_symbol_set()

    def _build_symbol_set(self) -> set[str]:
        """Build a set of all known code symbols (lowercase for matching)."""
        symbols: set[str] = set()

        for name in self.ctx.classes:
            symbols.add(name.lower())
        for name in self.ctx.functions:
            symbols.add(name.lower())
        for mod in self.ctx.modules:
            symbols.add(mod.lower())
            # Also add the last component (e.g. "cli" from "todocs.cli")
            parts = mod.split(".")
            if parts:
                symbols.add(parts[-1].lower())
        for cmd in self.ctx.cli_commands:
            symbols.add(cmd.lower())
        for ep in self.ctx.endpoints:
            symbols.add(ep.lower())
        for dep in self.ctx.dependencies:
            symbols.add(dep.lower())
        for src in self.ctx.src_files:
            symbols.add(src.lower())

        return symbols

    def validate(self, doc_files: list[DocFile]):
        """Check each chunk for references to code symbols."""
        for doc_file in doc_files:
            for chunk in doc_file.chunks:
                if chunk.status in (ChunkStatus.EMPTY, ChunkStatus.DUPLICATE):
                    continue  # Already resolved
                self._check_code_references(chunk)
                self._check_import_paths(chunk)
                self._check_cli_commands(chunk)

    def _check_code_references(self, chunk: DocChunk):
        """Check inline code references like `ClassName` or `function_name`."""
        # Extract backtick-quoted code references
        code_refs = re.findall(r"`([A-Za-z_]\w*(?:\.\w+)*)`", chunk.content)

        orphaned_refs: list[str] = []
        for ref in code_refs:
            ref_lower = ref.lower()
            # Check if any part of the reference matches known symbols
            parts = ref_lower.split(".")
            if any(p in self._known_symbols for p in parts):
                continue
            if ref_lower in self._known_symbols:
                continue

            # Skip common non-code references
            if ref_lower in _COMMON_NON_CODE:
                continue

            # Skip very short references (likely formatting)
            if len(ref) < 3:
                continue

            orphaned_refs.append(ref)

        if orphaned_refs and len(orphaned_refs) >= 2:
            chunk.add_issue(
                "orphaned_code_ref",
                Severity.WARNING,
                f"References {len(orphaned_refs)} unknown code symbol(s): "
                f"{', '.join(orphaned_refs[:5])}",
                suggestion="These may be outdated API references or typos",
            )
            if chunk.status == ChunkStatus.UNCHECKED:
                chunk.status = ChunkStatus.ORPHANED
                chunk.action = ActionType.FLAG
                chunk.confidence = 0.6
                chunk.validator = "crossref:orphaned_code"

    def _check_import_paths(self, chunk: DocChunk):
        """Check Python import statements in code blocks."""
        import_re = re.compile(
            r"(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))"
        )

        # Only check inside code blocks
        code_block_re = re.compile(r"```(?:python|py)?\n(.*?)```", re.DOTALL)
        for block_match in code_block_re.finditer(chunk.content):
            block = block_match.group(1)
            for imp_match in import_re.finditer(block):
                module = imp_match.group(1) or imp_match.group(2)
                if not module:
                    continue

                # Check if this is a project-internal import
                root_package = module.split(".")[0]
                is_internal = any(
                    src.startswith(root_package + "/") or src.startswith(root_package + ".")
                    for src in self.ctx.src_files
                )

                if is_internal and module.lower() not in self._known_symbols:
                    # Check partial match
                    parts = module.lower().split(".")
                    if not any(p in self._known_symbols for p in parts):
                        chunk.add_issue(
                            "broken_import",
                            Severity.ERROR,
                            f"Code example imports '{module}' which doesn't exist in project",
                            suggestion="Update the import path or remove the example",
                        )

    def _check_cli_commands(self, chunk: DocChunk):
        """Check CLI command references in code blocks."""
        if not self.ctx.cli_commands:
            return

        for line in self._iter_cli_code_lines(chunk.content):
            self._check_cli_line(chunk, line)

    def _iter_cli_code_lines(self, content: str):
        """Yield lines from bash-like fenced code blocks."""
        for block_match in _CLI_CODE_BLOCK_RE.finditer(content):
            yield from block_match.group(1).splitlines()

    def _check_cli_line(self, chunk: DocChunk, line: str):
        """Check one shell-like line for stale project CLI usage."""
        line = line.strip()
        if not line or line.startswith("#"):
            return

        words = line.split()
        if not words:
            return

        cmd = words[0]
        if self._line_contains_known_cli(line) or self._is_common_shell_command(cmd):
            return

        potential_cli = self._potential_cli_invocation(cmd, words)
        if not potential_cli:
            return

        if self._matches_known_cli(cmd, potential_cli):
            chunk.add_issue(
                "cli_command",
                Severity.WARNING,
                f"CLI command '{potential_cli}' may be outdated or incorrect",
                suggestion=f"Verify: project CLI commands are: {', '.join(self.ctx.cli_commands[:5])}",
            )

    def _line_contains_known_cli(self, line: str) -> bool:
        """Return True when a line already references a known CLI command."""
        return any(known_cmd in line for known_cmd in self.ctx.cli_commands)

    def _is_common_shell_command(self, cmd: str) -> bool:
        """Return True for shell commands that should not be treated as project CLIs."""
        return cmd in _COMMON_SHELL_COMMANDS

    def _potential_cli_invocation(self, cmd: str, words: list[str]) -> str:
        """Build a candidate CLI invocation from a shell line."""
        if len(words) < 2 or not cmd.isalnum():
            return ""
        return f"{cmd} {words[1]}"

    def _matches_known_cli(self, cmd: str, potential_cli: str) -> bool:
        """Return True when the candidate looks like a project CLI invocation."""
        return any(
            cmd == known or potential_cli.startswith(known)
            for known in self.ctx.cli_commands
        )


# Common backtick-quoted terms that aren't code references
_COMMON_NON_CODE = {
    "true", "false", "null", "none", "yes", "no",
    "string", "int", "float", "bool", "dict", "list", "tuple",
    "get", "post", "put", "delete", "patch",
    "master", "main", "develop", "dev", "prod", "staging",
    "bash", "shell", "python", "node", "npm", "pip",
    "readme", "changelog", "license", "todo", "fixme",
    "example", "default", "config", "settings", "env",
}


_CLI_CODE_BLOCK_RE = re.compile(r"```(?:bash|shell|sh)?\n(.*?)```", re.DOTALL)


_COMMON_SHELL_COMMANDS = {
    "cd", "ls", "cat", "echo", "mkdir", "rm", "cp", "mv",
    "git", "python", "pip", "npm", "node", "make", "docker",
    "tar", "zip", "unzip", "curl", "wget", "ssh", "scp",
    "chmod", "chown", "find", "grep", "awk", "sed",
    "source", "export", "unset", "env", "set",
}
