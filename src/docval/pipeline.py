"""Main validation pipeline — orchestrates discover → chunk → validate → report."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .chunker import chunk_directory
from .context import build_context
from .models import ValidationResult
from .validators.heuristic import HeuristicValidator
from .validators.crossref import CrossRefValidator


def scan(
    docs_dir: Path,
    project_root: Path | None = None,
    exclude: list[str] | None = None,
    use_llm: bool = False,
    llm_model: str = "gpt-4o-mini",
    verbose: bool = False,
) -> ValidationResult:
    """Run the full validation pipeline.

    Args:
        docs_dir: Path to the documentation directory
        project_root: Path to the project root (for code cross-referencing).
                      Defaults to docs_dir parent.
        exclude: Directory names to exclude from scanning
        use_llm: Whether to use LLM for semantic validation
        llm_model: LiteLLM model identifier
        verbose: Print progress information

    Returns:
        ValidationResult with all findings
    """
    if project_root is None:
        project_root = docs_dir.parent

    docs_dir = docs_dir.resolve()
    project_root = project_root.resolve()

    # Step 1: Build project context
    if verbose:
        print(f"Building project context from {project_root}...")
    ctx = build_context(project_root)

    if verbose:
        print(
            f"  Found {len(ctx.src_files)} source files, "
            f"{len(ctx.classes)} classes, "
            f"{len(ctx.functions)} functions"
        )

    # Step 2: Discover and chunk markdown files
    if verbose:
        print(f"Scanning documentation in {docs_dir}...")

    doc_files = chunk_directory(docs_dir, exclude_patterns=exclude)

    total_chunks = sum(len(f.chunks) for f in doc_files)
    if verbose:
        print(f"  Found {len(doc_files)} files, {total_chunks} sections")

    # Step 3: Heuristic validation (fast, no LLM)
    if verbose:
        print("Running heuristic validation...")

    heuristic = HeuristicValidator(ctx=ctx)
    heuristic.validate(doc_files)

    # Step 4: Cross-reference validation
    if verbose:
        print("Checking code cross-references...")

    crossref = CrossRefValidator(ctx=ctx)
    crossref.validate(doc_files)

    # Step 5: LLM validation (optional, only for uncertain chunks)
    if use_llm:
        if verbose:
            print(f"Running LLM validation with {llm_model}...")

        from .validators.llm_validator import LLMValidator
        llm = LLMValidator(model=llm_model, ctx=ctx, llm_error_threshold=0.7)
        validated = llm.validate(doc_files, only_uncertain=True)

        if verbose:
            print(f"  LLM validated {validated} chunks")

    # Build result
    result = ValidationResult(doc_files=doc_files)
    result.update_counts()

    return result
