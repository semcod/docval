"""Generate JSON validation report for CI/CD integration."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import ValidationResult


class JSONReporter:
    """Generate a JSON report of validation results."""

    def report(self, result: ValidationResult, output: Path):
        """Write validation report as JSON."""
        result.update_counts()

        data = {
            "summary": {
                "files_scanned": result.files_scanned,
                "chunks_total": result.chunks_total,
                "chunks_valid": result.chunks_valid,
                "chunks_invalid": result.chunks_invalid,
                "chunks_outdated": result.chunks_outdated,
                "chunks_duplicate": result.chunks_duplicate,
                "chunks_orphaned": result.chunks_orphaned,
                "chunks_empty": result.chunks_empty,
                "health_pct": round(
                    result.chunks_valid / result.chunks_total * 100, 1
                ) if result.chunks_total else 0,
            },
            "files": [],
        }

        for doc_file in result.doc_files:
            file_data = {
                "path": doc_file.relative_path,
                "total_lines": doc_file.total_lines,
                "status": doc_file.worst_status.value,
                "chunks": [],
            }

            for chunk in doc_file.chunks:
                chunk_data = {
                    "heading": chunk.heading,
                    "level": chunk.heading_level,
                    "lines": f"{chunk.line_start}-{chunk.line_end}",
                    "status": chunk.status.value,
                    "action": chunk.action.value,
                    "confidence": round(chunk.confidence, 2),
                    "validator": chunk.validator,
                    "issues": [
                        {
                            "rule": i.rule,
                            "severity": i.severity.value,
                            "message": i.message,
                            "suggestion": i.suggestion,
                        }
                        for i in chunk.issues
                    ],
                }
                file_data["chunks"].append(chunk_data)

            data["files"].append(file_data)

        output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
