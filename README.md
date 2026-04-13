# docval

[![Python](https://img.shields.io/badge/python-3.10+-3776AB)](https://python.org)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://img.shields.io/badge/tests-37%20passed-brightgreen)](tests/)


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.1.1-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.15-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-1.0h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.1500 (1 commits)
- 👤 **Human dev:** ~$100 (1.0h @ $100/h, 30min dedup)

Generated on 2026-04-13 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---



Validate and refactor Markdown documentation against source code — detect outdated, orphaned, duplicate, and invalid docs using heuristics + optional LLM.

![docval_architecture.svg](../../../Downloads/docval_architecture.svg)

## How it works

```
docs/  ──→  chunk by heading  ──→  heuristic checks  ──→  cross-ref with code  ──→  (optional) LLM  ──→  report/fix
```

**Three validation layers**, each progressively deeper:

1. **Heuristic validator** (fast, free) — empty sections, broken internal links, TODO/FIXME markers, duplicate detection via `difflib`, stale version references, archive path detection, explicit deprecation markers
2. **Cross-reference validator** (fast, free) — checks that backtick-quoted symbols (`ClassName`, `function_name`), import paths in code blocks, and CLI commands actually exist in the project source
3. **LLM validator** (optional, paid) — semantic validation via `litellm` for chunks that heuristics couldn't resolve with high confidence

## Installation

```bash
pip install docval
```

With LLM support:

```bash
pip install docval[llm]
```

From source:

```bash
git clone https://github.com/wronai/docval.git
cd docval
pip install -e ".[dev]"
```

## CLI Usage

### Scan and report issues

```bash
docval scan docs/
docval scan docs/ --project /path/to/repo -v
docval scan docs/ -o report.md
docval scan docs/ -o report.json
```

### Fix documentation (dry-run by default)

```bash
docval fix docs/                           # preview changes
docval fix docs/ --no-dry-run              # apply fixes
docval fix docs/ --no-dry-run --llm        # with LLM validation
```

### Generate a patch file

```bash
docval patch docs/ -o fixes.txt
docval patch docs/ --llm --model gpt-4o -o fixes.txt
```

### View documentation statistics

```bash
docval stats docs/
```

### LLM validation

```bash
export OPENAI_API_KEY=sk-...
docval scan docs/ --llm --model gpt-4o-mini
docval scan docs/ --llm --model anthropic/claude-sonnet-4-20250514
docval scan docs/ --llm --model groq/llama-3.3-70b-versatile
```

Any model supported by [litellm](https://docs.litellm.ai/) works.

## Python API

```python
from pathlib import Path
from docval.pipeline import scan
from docval.reporters import ConsoleReporter, MarkdownReporter

# Run validation
result = scan(
    docs_dir=Path("docs/"),
    project_root=Path("."),
    use_llm=False,
)

# Print to console
ConsoleReporter(verbose=True).report(result)

# Write markdown report
MarkdownReporter().report(result, Path("validation-report.md"))
```

### Using individual validators

```python
from docval.chunker import chunk_directory
from docval.context import build_context
from docval.validators import HeuristicValidator, CrossRefValidator

# Chunk docs
doc_files = chunk_directory(Path("docs/"))

# Build project context
ctx = build_context(Path("."))

# Run heuristics
heuristic = HeuristicValidator(ctx=ctx)
heuristic.validate(doc_files)

# Cross-reference check
crossref = CrossRefValidator(ctx=ctx)
crossref.validate(doc_files)

# Inspect results
for f in doc_files:
    for chunk in f.chunks:
        if chunk.issues:
            print(f"{f.relative_path}:{chunk.line_start} [{chunk.status.value}] {chunk.heading}")
            for issue in chunk.issues:
                print(f"  {issue.severity.value}: {issue.message}")
```

## What it detects

| Check | Layer | Example |
|-------|-------|---------|
| Empty sections | Heuristic | Heading with no body text |
| Broken internal links | Heuristic | `[guide](./deleted-file.md)` |
| Deprecated markers | Heuristic | `DEPRECATED`, `OBSOLETE`, `DO NOT USE` |
| Archive path | Heuristic | Files in `docs/archive/` directories |
| Stale versions | Heuristic | References to v1.x when project is v3.x |
| Duplicates | Heuristic | >80% similar content across files |
| TODO/FIXME | Heuristic | Unfinished documentation markers |
| Orphaned code refs | CrossRef | `` `NonExistentClass` `` in backticks |
| Broken imports | CrossRef | `from mypackage.deleted import X` in code blocks |
| Semantic accuracy | LLM | Content that doesn't match actual project behavior |

## Architecture

```
src/docval/
├── cli.py                  # Click CLI: scan, fix, patch, stats
├── pipeline.py             # Orchestrates: discover → chunk → validate → report
├── models.py               # Data models: DocChunk, DocFile, ValidationResult
├── chunker.py              # MD → heading-based semantic chunks
├── context.py              # Build project context (AST, git, .toon files)
├── validators/
│   ├── heuristic.py        # Rule-based checks (free, fast)
│   ├── crossref.py         # Code ↔ docs cross-reference
│   └── llm_validator.py    # Semantic validation via litellm
├── actions/
│   └── executor.py         # Apply fixes: delete, archive, patch
└── reporters/
    ├── console.py           # Rich CLI output
    ├── markdown_report.py   # .md report
    └── json_report.py       # .json for CI/CD
```

## Integration with .toon files

docval understands `.toon.yaml` files from the [code2llm](https://github.com/wronai/code2llm) ecosystem. When present, it extracts module names, class names, and exported functions for cross-referencing, giving more accurate orphaned-reference detection.

## License

Licensed under Apache-2.0.
