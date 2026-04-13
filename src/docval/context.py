"""Build project context from source code, git, and .toon files."""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import yaml

from .models import ProjectContext


def build_context(project_root: Path, max_depth: int = 4) -> ProjectContext:
    """Gather project context for cross-referencing with documentation.

    Extracts: source files, class/function names, CLI commands,
    recent git commits, .toon file data, dependency names, version.
    """
    ctx = ProjectContext(root=project_root)

    _collect_src_files(ctx, project_root, max_depth)
    _extract_python_symbols(ctx, project_root)
    _extract_version(ctx, project_root)
    _extract_dependencies(ctx, project_root)
    _parse_toon_files(ctx, project_root)
    _collect_git_info(ctx, project_root)
    _build_dir_tree(ctx, project_root)

    return ctx


def _collect_src_files(ctx: ProjectContext, root: Path, max_depth: int):
    """Collect source file paths (Python, JS, Go, Rust, etc.)."""
    extensions = {".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php", ".c", ".cpp", ".h"}
    skip_dirs = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".tox"}

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs and not d.startswith(".")
        ]

        depth = len(Path(dirpath).relative_to(root).parts)
        if depth > max_depth:
            dirnames.clear()
            continue

        for f in filenames:
            if Path(f).suffix in extensions:
                rel = str(Path(dirpath, f).relative_to(root))
                ctx.src_files.append(rel)


def _extract_python_symbols(ctx: ProjectContext, root: Path):
    """Extract class and function names from Python files using AST."""
    for src in ctx.src_files:
        if not src.endswith(".py"):
            continue
        filepath = root / src
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue

        module_name = src.replace("/", ".").replace("\\", ".").removesuffix(".py")
        ctx.modules.append(module_name)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                ctx.classes.append(node.name)
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if not node.name.startswith("_"):
                    ctx.functions.append(node.name)

            # Detect Click/Typer CLI commands
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    dec_name = _decorator_name(dec)
                    if dec_name and ("command" in dec_name or "group" in dec_name):
                        ctx.cli_commands.append(node.name)

            # Detect REST endpoints
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    dec_name = _decorator_name(dec)
                    if dec_name and any(
                        m in dec_name for m in (".get", ".post", ".put", ".delete", ".patch", ".route")
                    ):
                        ctx.endpoints.append(node.name)


def _decorator_name(dec) -> str:
    """Extract decorator name as a string."""
    if isinstance(dec, ast.Name):
        return dec.id
    elif isinstance(dec, ast.Attribute):
        parts = []
        node = dec
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))
    elif isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    return ""


def _extract_version(ctx: ProjectContext, root: Path):
    """Extract project version from pyproject.toml or package.json."""
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                tomllib = None  # type: ignore

        if tomllib:
            try:
                data = tomllib.loads(pyproject.read_text())
                ctx.version = data.get("project", {}).get("version", "")
            except Exception:
                pass

    if not ctx.version:
        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                import json
                data = json.loads(pkg_json.read_text())
                ctx.version = data.get("version", "")
            except Exception:
                pass


def _extract_dependencies(ctx: ProjectContext, root: Path):
    """Extract dependency names from pyproject.toml or requirements.txt."""
    dep_re = re.compile(r"^([a-zA-Z0-9_-]+)")

    reqs = root / "requirements.txt"
    if reqs.exists():
        try:
            for line in reqs.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    m = dep_re.match(line)
                    if m:
                        ctx.dependencies.append(m.group(1))
        except OSError:
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
            # Simple regex extraction of dependency names
            for m in re.finditer(r'"([a-zA-Z0-9_-]+)(?:\[.*?\])?(?:[><=!~].*?)?"', text):
                name = m.group(1)
                if name not in ctx.dependencies and len(name) > 1:
                    ctx.dependencies.append(name)
        except OSError:
            pass


def _parse_toon_files(ctx: ProjectContext, root: Path):
    """Parse .toon.yaml files for code analysis data."""
    toon_files = list(root.rglob("*.toon.yaml")) + list(root.rglob("*.toon"))
    for tf in toon_files:
        try:
            text = tf.read_text(encoding="utf-8")
            # Extract key metrics and symbols from toon files
            data = {"file": str(tf.relative_to(root)), "raw": text[:3000]}

            # Extract module names from M[...] lines
            for m in re.finditer(r"M\[([^\]]+)\]", text):
                mod = m.group(1).strip()
                if mod not in ctx.modules:
                    ctx.modules.append(mod)

            # Extract class names from class lines
            for m in re.finditer(r"^\s+(\w+):\s+__init__", text, re.MULTILINE):
                cls = m.group(1)
                if cls not in ctx.classes:
                    ctx.classes.append(cls)

            # Extract exported symbols
            for m in re.finditer(r"e:\s+(.+)$", text, re.MULTILINE):
                for sym in m.group(1).split(","):
                    sym = sym.strip()
                    if sym and sym not in ctx.functions:
                        ctx.functions.append(sym)

            ctx.toon_data[tf.name] = data
        except (OSError, UnicodeDecodeError):
            continue


def _collect_git_info(ctx: ProjectContext, root: Path):
    """Collect recent git commit messages."""
    try:
        import git as gitpython
        repo = gitpython.Repo(root, search_parent_directories=True)
        for commit in repo.iter_commits("HEAD", max_count=10):
            msg = commit.message.strip().split("\n")[0]
            ctx.recent_commits.append(msg)
    except Exception:
        # Fallback to subprocess
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=root, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                ctx.recent_commits = result.stdout.strip().splitlines()
        except Exception:
            pass


def _build_dir_tree(ctx: ProjectContext, root: Path, max_depth: int = 2):
    """Build a compact directory tree string."""
    try:
        result = subprocess.run(
            ["find", str(root), "-maxdepth", str(max_depth), "-type", "f",
             "-not", "-path", "*/.git/*", "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/__pycache__/*"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            files = sorted(result.stdout.strip().splitlines())
            ctx.dir_tree = "\n".join(
                str(Path(f).relative_to(root)) for f in files[:100]
            )
    except Exception:
        ctx.dir_tree = "\n".join(ctx.src_files[:50])
