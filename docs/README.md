<!-- code2docs:start --># docval

![version](https://img.shields.io/badge/version-0.1.0-blue) ![python](https://img.shields.io/badge/python-%3E%3D3.10-blue) ![coverage](https://img.shields.io/badge/coverage-unknown-lightgrey) ![functions](https://img.shields.io/badge/functions-56-green)
> **56** functions | **16** classes | **17** files | CC̄ = 6.3

> Auto-generated project documentation from source code analysis.

**Author:** Tom Sapletta  
**License:** Apache-2.0[(LICENSE)](./LICENSE)  
**Repository:** [https://github.com/semcod/docval](https://github.com/semcod/docval)

### From PyPI

```bash
pip install docval
```

### From Source

```bash
git clone https://github.com/semcod/docval
cd docval
pip install -e .
```

### Optional Extras

```bash
pip install docval[llm]    # LLM integration (litellm)
pip install docval[all]    # all optional features
pip install docval[dev]    # development tools
```

# Only regenerate README
docval ./my-project --readme-only

# Preview what would be generated (no file writes)
docval ./my-project --dry-run

# Check documentation health
docval check ./my-project

# Sync — regenerate only changed modules
docval sync ./my-project
```

### Python API

```python
from docval import generate_readme, generate_docs, Code2DocsConfig

# Quick: generate README
generate_readme("./my-project")

# Full: generate all documentation
config = Code2DocsConfig(project_name="mylib", verbose=True)
docs = generate_docs("./my-project", config=config)
```

## Generated Output

When you run `docval`, the following files are produced:

```
<project>/
├── README.md                 # Main project README (auto-generated sections)
├── docs/
│   ├── api.md               # Consolidated API reference
│   ├── modules.md           # Module documentation with metrics
│   ├── architecture.md      # Architecture overview with diagrams
│   ├── dependency-graph.md  # Module dependency graphs
│   ├── coverage.md          # Docstring coverage report
│   ├── getting-started.md   # Getting started guide
│   ├── configuration.md    # Configuration reference
│   └── api-changelog.md    # API change tracking
├── examples/
│   ├── quickstart.py       # Basic usage examples
│   └── advanced_usage.py   # Advanced usage examples
├── CONTRIBUTING.md         # Contribution guidelines
└── mkdocs.yml             # MkDocs site configuration
```

## Configuration

Create `docval.yaml` in your project root (or run `docval init`):

```yaml
project:
  name: my-project
  source: ./
  output: ./docs/

readme:
  sections:
    - overview
    - install
    - quickstart
    - api
    - structure
  badges:
    - version
    - python
    - coverage
  sync_markers: true

docs:
  api_reference: true
  module_docs: true
  architecture: true
  changelog: true

examples:
  auto_generate: true
  from_entry_points: true

sync:
  strategy: markers    # markers | full | git-diff
  watch: false
  ignore:
    - "tests/"
    - "__pycache__"
```

## Sync Markers

docval can update only specific sections of an existing README using HTML comment markers:

```markdown
<!-- docval:start -->
# Project Title
... auto-generated content ...
<!-- docval:end -->
```

Content outside the markers is preserved when regenerating. Enable this with `sync_markers: true` in your configuration.

## Architecture

```
docval/
├── project    ├── docval/        ├── chunker        ├── cli        ├── pipeline        ├── actions/        ├── context        ├── validators/            ├── llm_validator            ├── heuristic        ├── reporters/            ├── crossref            ├── markdown_report            ├── json_report            ├── console            ├── executor        ├── models```

### Classes

- **`LLMValidator`** — Validate documentation chunks using an LLM via litellm.
- **`HeuristicValidator`** — Apply fast heuristic rules to doc chunks before LLM validation.
- **`CrossRefValidator`** — Validate documentation references against actual project code.
- **`MarkdownReporter`** — Generate a Markdown report of validation results.
- **`JSONReporter`** — Generate a JSON report of validation results.
- **`ConsoleReporter`** — Print validation results to the console using rich.
- **`ActionResult`** — Summary of executed actions.
- **`ActionExecutor`** — Execute remediation actions on doc files.
- **`ChunkStatus`** — —
- **`ActionType`** — —
- **`Severity`** — —
- **`Issue`** — A single validation issue found in a doc chunk.
- **`DocChunk`** — A semantic chunk extracted from a Markdown file.
- **`DocFile`** — Represents a single Markdown file with its chunks.
- **`ProjectContext`** — Gathered context about the project for cross-referencing.
- **`ValidationResult`** — Aggregated result of a validation run.

### Functions

- `chunk_file(path, base_dir)` — Parse a single Markdown file into heading-based chunks.
- `discover_md_files(docs_dir, exclude_patterns)` — Recursively find all .md files, excluding node_modules, .git, etc.
- `chunk_directory(docs_dir, exclude_patterns)` — Chunk all Markdown files in a directory.
- `main()` — Validate and refactor Markdown documentation against source code.
- `scan(docs_dir, project, exclude, llm)` — Scan documentation and report issues.
- `fix(docs_dir, project, exclude, force)` — Validate and apply fixes to documentation.
- `patch(docs_dir, project, exclude, output)` — Generate a patch file with recommended changes.
- `stats(docs_dir, exclude)` — Show documentation statistics (no validation).
- `scan(docs_dir, project_root, exclude, use_llm)` — Run the full validation pipeline.
- `build_context(project_root, max_depth)` — Gather project context for cross-referencing with documentation.


## Project Structure

📄 `project`
📦 `src.docval`
📦 `src.docval.actions`
📄 `src.docval.actions.executor` (5 functions, 2 classes)
📄 `src.docval.chunker` (3 functions)
📄 `src.docval.cli` (5 functions)
📄 `src.docval.context` (9 functions)
📄 `src.docval.models` (3 functions, 8 classes)
📄 `src.docval.pipeline` (1 functions)
📦 `src.docval.reporters`
📄 `src.docval.reporters.console` (6 functions, 1 classes)
📄 `src.docval.reporters.json_report` (1 functions, 1 classes)
📄 `src.docval.reporters.markdown_report` (1 functions, 1 classes)
📦 `src.docval.validators`
📄 `src.docval.validators.crossref` (6 functions, 1 classes)
📄 `src.docval.validators.heuristic` (10 functions, 1 classes)
📄 `src.docval.validators.llm_validator` (6 functions, 1 classes)

## Requirements

- Python >= >=3.10
- click >=8.1- rich >=13.0- pyyaml >=6.0- gitpython >=3.1

## Contributing

**Contributors:**
- Tom Sapletta <tom-sapletta-com@users.noreply.github.com>

We welcome contributions! Please see [CONTRIBUTING.md](https://github.com/wronai/docval/blob/main/CONTRIBUTING.md) for guidelines.

# Clone the repository
git clone https://github.com/semcod/docval
cd docval

# Install in development mode
pip install -e ".[dev]"

## Documentation

- 📖 [Full Documentation](https://github.com/semcod/docval/tree/main/docs) — API reference, module docs, architecture
- 🚀 [Getting Started](https://github.com/semcod/docval/blob/main/docs/getting-started.md) — Quick start guide
- 📚 [API Reference](https://github.com/semcod/docval/blob/main/docs/api.md) — Complete API documentation
- 🔧 [Configuration](https://github.com/semcod/docval/blob/main/docs/configuration.md) — Configuration options
- 💡 [Examples](https://github.com/wronai/docval/tree/main/examples) — Usage examples and code samples

### Generated Files

| Output | Description | Link |
|--------|-------------|------|
| `README.md` | Project overview (this file) | — |
| `docs/api.md` | Consolidated API reference | [View](https://github.com/wronai/docval/blob/main/docs/api.md) |
| `docs/modules.md` | Module reference with metrics | [View](https://github.com/wronai/docval/blob/main/docs/modules.md) |
| `docs/architecture.md` | Architecture with diagrams | [View](https://github.com/wronai/docval/blob/main/docs/architecture.md) |
| `docs/dependency-graph.md` | Dependency graphs | [View](https://github.com/wronai/docval/blob/main/docs/dependency-graph.md) |
| `docs/coverage.md` | Docstring coverage report | [View](https://github.com/wronai/docval/blob/main/docs/coverage.md) |
| `docs/getting-started.md` | Getting started guide | [View](https://github.com/wronai/docval/blob/main/docs/getting-started.md) |
| `docs/configuration.md` | Configuration reference | [View](https://github.com/wronai/docval/blob/main/docs/configuration.md) |
| `docs/api-changelog.md` | API change tracking | [View](https://github.com/wronai/docval/blob/main/docs/api-changelog.md) |
| `CONTRIBUTING.md` | Contribution guidelines | [View](https://github.com/wronai/docval/blob/main/CONTRIBUTING.md) |
| `examples/` | Usage examples | [Browse](https://github.com/wronai/docval/tree/main/examples) |
| `mkdocs.yml` | MkDocs configuration | — |

<!-- code2docs:end -->