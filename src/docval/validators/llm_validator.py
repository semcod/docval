"""LLM-based semantic validation using litellm.

Only validates chunks that heuristics couldn't resolve with high confidence.
Batches requests and respects rate limits.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from ..models import (
    ActionType,
    ChunkStatus,
    DocChunk,
    DocFile,
    ProjectContext,
    Severity,
)

# Map LLM status strings to our enums
_STATUS_MAP = {
    "valid": ChunkStatus.VALID,
    "invalid": ChunkStatus.INVALID,
    "outdated": ChunkStatus.OUTDATED,
    "duplicate": ChunkStatus.DUPLICATE,
    "orphaned": ChunkStatus.ORPHANED,
}

_ACTION_MAP = {
    "keep": ActionType.KEEP,
    "delete": ActionType.DELETE,
    "archive": ActionType.ARCHIVE,
    "fix": ActionType.FIX,
    "flag": ActionType.FLAG,
}


class LLMValidator:
    """Validate documentation chunks using an LLM via litellm."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        ctx: Optional[ProjectContext] = None,
        max_chunk_chars: int = 3000,
        delay_between_calls: float = 0.5,
        confidence_threshold: float = 0.75,
        llm_error_threshold: float = 0.5,
    ):
        self.model = model
        self.ctx = ctx
        self.max_chunk_chars = max_chunk_chars
        self.delay = delay_between_calls
        self.confidence_threshold = confidence_threshold
        self.llm_error_threshold = llm_error_threshold

    def validate(
        self,
        doc_files: list[DocFile],
        only_uncertain: bool = True,
        batch_size: int = 5,
    ) -> int:
        """Validate chunks via LLM. Returns number of chunks validated.

        Args:
            doc_files: Files to validate
            only_uncertain: If True, skip chunks already validated with high confidence
            batch_size: Number of chunks to batch in a single LLM call
        """
        try:
            from litellm import completion
        except ImportError:
            raise ImportError(
                "litellm is required for LLM validation. "
                "Install with: pip install docval[llm]"
            )

        context_str = self._build_context_summary()
        validated = 0

        # Collect chunks to validate
        chunks_to_validate = []
        for doc_file in doc_files:
            for chunk in doc_file.chunks:
                if only_uncertain and chunk.confidence >= self.confidence_threshold:
                    continue
                if chunk.status == ChunkStatus.EMPTY:
                    continue
                chunks_to_validate.append(chunk)

        # Process in batches
        for i in range(0, len(chunks_to_validate), batch_size):
            batch = chunks_to_validate[i:i + batch_size]
            if len(batch) == 1:
                # Single chunk validation (original behavior)
                result = self._validate_chunk(completion, batch[0], context_str)
                if result:
                    validated += 1
            else:
                # Batch validation
                result = self._validate_batch(completion, batch, context_str)
                if result:
                    validated += result

            if self.delay > 0:
                time.sleep(self.delay)

        return validated

    def _validate_batch(self, completion_fn, chunks: list[DocChunk], context_str: str) -> int:
        """Validate multiple chunks in a single LLM call. Returns number validated."""
        prompt = self._build_batch_prompt(chunks, context_str)

        try:
            resp = completion_fn(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1500,
            )

            text = resp.choices[0].message.content
            results = self._parse_batch_response(text, chunks)

            validated = 0
            for chunk, result in zip(chunks, results):
                if result:
                    status = _STATUS_MAP.get(result.get("status", ""), None)
                    action = _ACTION_MAP.get(result.get("action", ""), None)
                    confidence = float(result.get("confidence", 0.8))

                    # Only apply error status if confidence is above threshold
                    if status in (ChunkStatus.INVALID, ChunkStatus.ORPHANED):
                        if confidence < self.llm_error_threshold:
                            status = ChunkStatus.VALID
                            action = ActionType.KEEP

                    if status:
                        chunk.status = status
                    if action:
                        chunk.action = action

                    chunk.confidence = confidence
                    chunk.validator = f"llm:{self.model}"

                    reason = result.get("reason", "")
                    if reason:
                        severity = Severity.ERROR if status in (
                            ChunkStatus.INVALID, ChunkStatus.ORPHANED
                        ) else Severity.WARNING
                        chunk.add_issue("llm_review", severity, reason)

                    suggestion = result.get("suggestion", "")
                    if suggestion and chunk.issues:
                        chunk.issues[-1].suggestion = suggestion

                    validated += 1

            return validated

        except Exception as e:
            for chunk in chunks:
                chunk.add_issue(
                    "llm_error", Severity.INFO,
                    f"LLM batch validation failed: {str(e)[:100]}"
                )
            return 0

    def _validate_chunk(self, completion_fn, chunk: DocChunk, context_str: str) -> bool:
        """Validate a single chunk via LLM. Returns True if successful."""
        prompt = self._build_prompt(chunk, context_str)

        try:
            resp = completion_fn(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )

            text = resp.choices[0].message.content
            parsed = self._parse_response(text)

            if parsed:
                status = _STATUS_MAP.get(parsed.get("status", ""), None)
                action = _ACTION_MAP.get(parsed.get("action", ""), None)
                confidence = float(parsed.get("confidence", 0.8))

                # Only apply error status if confidence is above threshold
                if status in (ChunkStatus.INVALID, ChunkStatus.ORPHANED):
                    if confidence < self.llm_error_threshold:
                        status = ChunkStatus.VALID
                        action = ActionType.KEEP

                if status:
                    chunk.status = status
                if action:
                    chunk.action = action

                chunk.confidence = confidence
                chunk.validator = f"llm:{self.model}"

                reason = parsed.get("reason", "")
                if reason:
                    severity = Severity.ERROR if status in (
                        ChunkStatus.INVALID, ChunkStatus.ORPHANED
                    ) else Severity.WARNING
                    chunk.add_issue("llm_review", severity, reason)

                suggestion = parsed.get("suggestion", "")
                if suggestion and chunk.issues:
                    chunk.issues[-1].suggestion = suggestion

                return True

        except Exception as e:
            chunk.add_issue(
                "llm_error", Severity.INFO,
                f"LLM validation failed: {str(e)[:100]}"
            )

        return False

    def _build_batch_prompt(self, chunks: list[DocChunk], context_str: str) -> str:
        """Build validation prompt for multiple chunks."""
        chunk_descriptions = []
        for i, chunk in enumerate(chunks):
            content = chunk.content[:self.max_chunk_chars // len(chunks)]
            chunk_descriptions.append(
                f"## Chunk {i+1}\n"
                f"File: {chunk.relative_path}\n"
                f"Section: {chunk.heading} (H{chunk.heading_level})\n"
                f"Lines: {chunk.line_start}-{chunk.line_end}\n\n"
                f"Content:\n---\n{content}\n---"
            )

        chunks_text = "\n\n".join(chunk_descriptions)
        return f"""Validate these {len(chunks)} documentation fragments against the project.

## Project context
{context_str}

## Documentation fragments
{chunks_text}

Respond ONLY with a JSON array (no markdown fences):
[
  {{
    "chunk": 1,
    "status": "valid|invalid|outdated|orphaned",
    "action": "keep|delete|archive|fix|flag",
    "confidence": 0.0-1.0,
    "reason": "brief explanation (max 50 words)",
    "suggestion": "what to fix if action is fix/flag (max 50 words)"
  }},
  ...
]

Rules:
- "valid": content is accurate and matches the project
- "invalid": contains factual errors, wrong API names, incorrect usage
- "outdated": references old versions, deprecated features, removed APIs
- "orphaned": references code/files/modules that don't exist in the project

Note: Example code snippets with placeholder names (e.g., "./my-project", "example.com") should NOT be flagged as invalid. Only flag actual code references that should exist but don't.
"""

    def _build_prompt(self, chunk: DocChunk, context_str: str) -> str:
        """Build the validation prompt for a single chunk."""
        content = chunk.content[:self.max_chunk_chars]

        existing_issues = ""
        if chunk.issues:
            existing_issues = "\nPrevious checks found:\n" + "\n".join(
                f"- [{i.severity.value}] {i.rule}: {i.message}" for i in chunk.issues
            )

        return f"""Validate this documentation fragment against the project.

## Project context
{context_str}

## Documentation fragment
File: {chunk.relative_path}
Section: {chunk.heading} (H{chunk.heading_level})
Lines: {chunk.line_start}-{chunk.line_end}
{existing_issues}

Content:
---
{content}
---

Respond ONLY with a JSON object (no markdown fences):
{{
  "status": "valid|invalid|outdated|orphaned",
  "action": "keep|delete|archive|fix|flag",
  "confidence": 0.0-1.0,
  "reason": "brief explanation (max 50 words)",
  "suggestion": "what to fix if action is fix/flag (max 50 words)"
}}

Rules:
- "valid": content is accurate and matches the project
- "invalid": contains factual errors, wrong API names, incorrect usage
- "outdated": references old versions, deprecated features, removed APIs
- "orphaned": references code/files/modules that don't exist in the project

Note: Example code snippets with placeholder names (e.g., "./my-project", "example.com") should NOT be flagged as invalid. Only flag actual code references that should exist but don't.
"""

    def _build_context_summary(self) -> str:
        """Build a compact project context string for the prompt."""
        if not self.ctx:
            return "(no project context available)"

        parts = [f"Project root: {self.ctx.root}"]

        if self.ctx.version:
            parts.append(f"Version: {self.ctx.version}")

        if self.ctx.classes:
            parts.append(f"Classes ({len(self.ctx.classes)}): {', '.join(self.ctx.classes[:20])}")

        if self.ctx.functions:
            parts.append(f"Public functions ({len(self.ctx.functions)}): {', '.join(self.ctx.functions[:20])}")

        if self.ctx.modules:
            parts.append(f"Modules ({len(self.ctx.modules)}): {', '.join(self.ctx.modules[:20])}")

        if self.ctx.cli_commands:
            parts.append(f"CLI commands: {', '.join(self.ctx.cli_commands)}")

        if self.ctx.dependencies:
            parts.append(f"Dependencies: {', '.join(self.ctx.dependencies[:15])}")

        if self.ctx.recent_commits:
            parts.append(f"Recent commits:\n  " + "\n  ".join(self.ctx.recent_commits[:5]))

        return "\n".join(parts)

    def _parse_batch_response(self, text: str, chunks: list[DocChunk]) -> list[dict | None]:
        """Parse JSON array from LLM batch response."""
        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())

        # Try to parse as JSON array
        try:
            results = json.loads(text)
            if isinstance(results, list):
                # Map results to chunks by chunk number
                chunk_results = [None] * len(chunks)
                for item in results:
                    chunk_num = item.get("chunk", 0) - 1  # 0-indexed
                    if 0 <= chunk_num < len(chunks):
                        chunk_results[chunk_num] = item
                return chunk_results
        except json.JSONDecodeError:
            pass

        # Fallback: return None for all chunks
        return [None] * len(chunks)

    def _parse_response(self, text: str) -> dict | None:
        """Parse JSON from LLM response, handling markdown fences."""
        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())

        # Try to extract JSON object
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Try the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None


_SYSTEM_PROMPT = """You are a documentation quality validator. You compare documentation fragments against actual project code and metadata to determine if the documentation is accurate, up-to-date, and useful.

Be strict but fair:
- Flag genuinely wrong information (wrong class names, incorrect API usage, etc.)
- Flag outdated references (old versions, removed features)
- Don't flag example code or placeholder projects as errors
- Don't flag planned features or beta features as errors unless explicitly marked as deprecated
- Don't flag minor style issues or formatting preferences
- Documentation that is technically correct but could be improved should be "valid" with a suggestion

Distinguish between:
- Actual code references: Should exist in the project
- Example code snippets: Can use placeholder names, don't need to exist
- Planned features: Mark as "valid" unless deprecated

Placeholder patterns to IGNORE (mark as valid):
- "./my-project", "example-project", "your-project"
- "example.com", "test.com", "localhost"
- "USERNAME", "PASSWORD", "API_KEY" (environment variables)
- Path patterns like "/path/to/file"
- Generic names like "MyClass", "MyFunction"

Always respond with valid JSON only. No markdown fences, no explanation outside JSON."""
