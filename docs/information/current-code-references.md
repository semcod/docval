---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "current-code-references",
  "kind": "information",
  "version": 2,
  "title": "Current source references in Docval",
  "status": "proposed",
  "owner": "semcod/docval",
  "created": "2026-09-09",
  "updated": "2026-09-09",
  "review_after": "2026-10-09",
  "source_revision": "855f0f25806ad7c575d0d0fe7d0ab69dd5faa3f5",
  "affected_repositories": [
    "semcod/docval"
  ],
  "evidence": [
    "https://github.com/semcod/docval/issues/6",
    "https://github.com/semcod/docval/blob/855f0f25806ad7c575d0d0fe7d0ab69dd5faa3f5/docs/information/current-code-references.md",
    "https://github.com/semcod/docval/blob/1debd415c95765c05ec9c975fdc1626943c05e1f/README.md",
    "https://github.com/semcod/docval/blob/1debd415c95765c05ec9c975fdc1626943c05e1f/src/docval/validators/crossref.py"
  ]
}
---

# Current source references in Docval

<!-- docs:section purpose -->
## Purpose

Make the documented cross-reference validator use the source context for the
current scan and identify missing internal modules in conventional Python layouts.

<!-- docs:section scope -->
## Scope

The correction owns `CrossRefValidator` and regression tests. Context extraction,
LLM behavior and automatic fix/export operations are unchanged.

<!-- docs:section evidence -->
## Observed discrepancies

The prior process-global cache keyed symbols by root and class/function counts.
Renaming two classes without changing their count left the old symbols accepted
and the new symbols reported as unknown. Dependencies, modules and commands were
not in that cache identity either. A fresh validator now builds its own symbol
set from the supplied context.

The old import check recognized a package only when a source path began with
its name. Consequently `src/example/api.py` did not establish `example` as
internal, and `from example.deleted import Client` passed without a finding.
Matching any known name in a dotted path could also hide a missing module.
The checker now compares full canonical module names, resolves conventional
`src/` layouts and retains namespace parents. An actual `src/__init__.py` keeps
`src` as the package name. External package roots remain outside this check.

Independent review also reproduced a false error in the initial correction:
context collection defaults to depth four, so an existing deeper module was
absent from the known-module set. Before reporting a missing module, the checker
now probes its Python source file or namespace directory in the project root
and, for a conventional source layout, `src/`. Resolved paths must remain within
the project root; symlinks outside that boundary are not accepted as evidence.

<!-- docs:section content -->
## Validation contract

For each scan, construct a new validator from its `ProjectContext`. Repeated
scans must not reuse symbol identities merely because counts match. Import
validation checks module presence in the supplied source context and uses bounded
filesystem probes for absent entries; it does not import or execute the candidate
project.

Regressions cover unchanged counts across six symbol categories, renamed and
removed symbols, flat/src/Windows-style paths, namespace packages, a real package
named src, external imports, modules beyond the context depth, missing deep
modules, and file/directory symlinks outside the project. The documented promise
of current-code validation predates this correction; the implementation is
repaired rather than weakening that promise in README.

<!-- docs:section limitations -->
## Limits

This is source-based checking, not proof of all runtime imports. Generated,
compiled, dynamically registered or custom-layout modules may need additional
context. Source probes cover conventional Python files and namespace directories;
they do not establish runtime importability or export availability. A diagnostic
alone does not authorize rewriting either code or docs.

<!-- docs:section next_actions -->
## Maintenance

Keep freshness and full-module matching in the regression suite. Changes to
source discovery require their own coverage evidence and review.
