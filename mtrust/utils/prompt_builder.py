# -*- coding: utf-8 -*-
"""
Prompt Builder
==============
Dynamically constructs a prompt string from a task spec (dict) and a runtime
context (dict).  No task-specific logic lives here — the spec drives everything.
"""

import json
from typing import Any


def build_prompt(spec: dict, context: dict, include_instruction: bool = True) -> str:
    """
    Build a prompt string from a spec and a runtime context.

    Spec expected keys:
        instruction  : str   — system / task instruction
        criteria     : list  — bullet-point rules fed to the model
        input_fields : list  — keys to pull from *context* and render as sections
        output_schema: dict  — keys with types, used to describe expected JSON shape

    context:
        Arbitrary dict whose keys must include everything listed in input_fields.

    include_instruction:
        When False, the instruction block is omitted (use when the caller sends
        instruction as a separate system-role message to avoid duplication).
    """

    lines: list[str] = []

    # ── 1. Instruction block ─────────────────────────────────────────────────
    if include_instruction:
        instruction = (spec.get("instruction") or "").strip()
        if instruction:
            lines.append(instruction)
            lines.append("")

    # ── 2. Input fields ──────────────────────────────────────────────────────
    input_fields: list[str] = spec.get("input_fields") or []
    for field in input_fields:
        label = field.replace("_", " ").upper()
        value = context.get(field, "")
        lines.append(f"【{label}】")
        lines.append(str(value))
        lines.append("")

    # ── 3. Criteria block ────────────────────────────────────────────────────
    criteria: list[str] = spec.get("criteria") or []
    if criteria:
        lines.append("【CRITERIA】")
        for i, rule in enumerate(criteria, 1):
            lines.append(f"{i}. {rule}")
        lines.append("")

    # ── 3b. Few-shot examples block ───────────────────────────────────────────
    # Each example: {label?, content fields matching input_fields, expected: {output fields}}
    examples: list[dict] = spec.get("examples") or []
    if examples:
        lines.append("【EXAMPLES】")
        lines.append("Use these examples to calibrate your judgment:")
        lines.append("")
        input_fields_set: list[str] = spec.get("input_fields") or []
        for idx, ex in enumerate(examples, 1):
            label = ex.get("label", f"Example {idx}")
            lines.append(f"── {label} ──")
            for field in input_fields_set:
                if field in ex:
                    field_label = field.replace("_", " ").upper()
                    lines.append(f"  [{field_label}] {ex[field]}")
            expected = ex.get("expected") or {}
            if expected:
                lines.append(f"  [EXPECTED OUTPUT] {json.dumps(expected, ensure_ascii=False)}")
            lines.append("")

    # ── 4. Output schema block ───────────────────────────────────────────────
    output_schema: dict[str, Any] = spec.get("output_schema") or {}
    if output_schema:
        lines.append("【OUTPUT】")
        lines.append("Return ONLY valid JSON with the following fields:")
        schema_lines = ["{"]
        for key, type_hint in output_schema.items():
            schema_lines.append(f'  "{key}": <{type_hint}>')
        schema_lines.append("}")
        lines.append("\n".join(schema_lines))

    return "\n".join(lines)
