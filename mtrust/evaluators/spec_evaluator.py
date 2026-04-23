# -*- coding: utf-8 -*-
"""
Spec Evaluator
==============
A generic evaluator fully driven by a task spec YAML file.
No task-specific field names exist in this module.

Usage:
    evaluator = SpecEvaluator("audit_false_positive")
    result    = evaluator.evaluate({"content": "...", "audit_result": "..."})

    evaluator = SpecEvaluator("qa_correctness")
    result    = evaluator.evaluate({"question": "...", "answer": "..."})
"""
import re
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from mtrust.llm_service import call_llm
from mtrust.utils.prompt_builder import build_prompt

logger = logging.getLogger(__name__)

_DEFAULT_SPEC_DIR = Path(__file__).parent.parent / "specs" / "06_evaluator"

# Field names considered "reason-like" for fallback text injection
_REASON_LIKE_FIELDS = {"reason", "explanation", "message", "detail", "rationale", "summary"}


class SpecEvaluator:
    """
    Loads a task spec from YAML, builds a prompt, calls the LLM, and parses
    the structured JSON response.

    All task-specific behaviour is controlled by the YAML spec:

        early_exit_rules:            # optional list of short-circuit conditions
          - field: error_type
            value: system_error
            result:                  # returned verbatim when condition matches
              confidence: 0.0
              reason: "system error - skipped"

        post_process:                # optional list of field-level guards
          - if_field: has_false_positive
            if_true: true
            confidence_field: confidence
            min_confidence: 0.35
            then_set:
              has_false_positive: false
    """

    def __init__(self, task_name: str, spec_dir: str | Path | None = None):
        self.task_name = task_name
        spec_dir = Path(spec_dir) if spec_dir else _DEFAULT_SPEC_DIR
        spec_path = spec_dir / f"{task_name}.yaml"

        if not spec_path.exists():
            raise FileNotFoundError(f"Spec not found: {spec_path}")

        with open(spec_path, "r", encoding="utf-8") as f:
            self.spec: dict = yaml.safe_load(f)

        # Pre-cache the output_schema field list for normalisation
        self._output_fields: dict[str, str] = self.spec.get("output_schema") or {}

        logger.debug("Loaded spec for task '%s' from %s", task_name, spec_path)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def evaluate(self, context: dict) -> dict:
        """
        Full evaluation cycle:  context → early-exit? → prompt → LLM → parse → post-process
        """
        # ── 1. Early exits (spec-driven) ──────────────────────────────────
        early = self._check_early_exit(context)
        if early is not None:
            return early

        # ── 2. Build prompt ───────────────────────────────────────────────
        # instruction → system role (higher authority, stable persona)
        # input_fields + criteria + output_schema → user role (runtime context)
        system_prompt: str | None = (self.spec.get("instruction") or "").strip() or None
        prompt = build_prompt(self.spec, context, include_instruction=False)
        logger.debug(
            "Prompt for '%s': system=%d chars, user=%d chars",
            self.task_name,
            len(system_prompt) if system_prompt else 0,
            len(prompt),
        )

        # ── 3. Call LLM ───────────────────────────────────────────────────
        print(f"🔥 LLM CALLED [{self.task_name}]")
        try:
            raw = call_llm(prompt, system_prompt=system_prompt)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return self._error_result(str(exc))

        print(f"🔥 LLM RAW RESPONSE: {raw[:150]}")

        # ── 4. Parse + normalise ──────────────────────────────────────────
        parsed = self._parse(raw)
        #print(f"🔥 PARSED RESULT (pre-postprocess): {parsed}")

        # ── 5. Post-process (spec-driven) ─────────────────────────────────
        parsed = self._apply_post_process(parsed)
        print(f"🔥 FINAL RESULT (post-postprocess): {parsed}")

        return parsed

    # ------------------------------------------------------------------ #
    # Spec-driven helpers
    # ------------------------------------------------------------------ #

    def _check_early_exit(self, context: dict) -> dict | None:
        """
        Evaluates early_exit_rules from the spec.
        Returns the result dict if a rule matches, else None.
        """
        for rule in self.spec.get("early_exit_rules") or []:
            field = rule.get("field", "")
            expected = rule.get("value")
            if context.get(field) == expected:
                logger.debug("Early exit triggered: %s == %s", field, expected)
                return dict(rule.get("result") or {})
        return None

    def _apply_post_process(self, result: dict) -> dict:
        """
        Applies post_process rules from the spec.

        Each rule shape:
            if_field:         <field to check>
            if_true:          <value that triggers the guard>
            confidence_field: <field holding the confidence score>
            min_confidence:   <threshold below which we override>
            then_set:         <dict of field: value overrides>

        NOTE: if_true comparison is type-tolerant — both sides are normalised
        to lowercase strings so YAML `true` and Python `True` always match.
        """
        for rule in self.spec.get("post_process") or []:
            if_field = rule.get("if_field")
            if_true = rule.get("if_true")
            conf_field = rule.get("confidence_field")
            min_conf = rule.get("min_confidence")
            then_set: dict = rule.get("then_set") or {}

            # ── Type-tolerant equality check ──────────────────────────────
            # Normalise both sides to lowercase string so that:
            #   YAML `true`  == Python `True` == string `"true"` == `"True"`
            actual_val = result.get(if_field)
            actual_str = str(actual_val).lower() if actual_val is not None else ""
            expect_str = str(if_true).lower() if if_true is not None else ""
            if actual_str != expect_str:
                continue

            # ── Confidence guard ──────────────────────────────────────────
            if conf_field and min_conf is not None:
                try:
                    current_conf = float(result.get(conf_field, 0))
                    threshold = float(min_conf)
                    if current_conf >= threshold:
                        logger.debug(
                            "post_process: SKIPPED (confidence %.3f >= threshold %.3f)",
                            current_conf, threshold,
                        )
                        continue   # confidence is high enough → do NOT override
                    logger.warning(
                        "post_process: OVERRIDING because confidence %.3f < threshold %.3f",
                        current_conf, threshold,
                    )
                except (TypeError, ValueError):
                    pass

            # ── Apply overrides ───────────────────────────────────────────
            for k, v in then_set.items():
                logger.debug("post_process: set %s = %r  (was %r)", k, v, result.get(k))
                result[k] = v

        return result

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    def _parse(self, raw: str) -> dict:
        try:
            clean = self._extract_json(raw)
            data = json.loads(clean)
            return self._normalize(data, raw)
        except Exception as exc:
            logger.warning("JSON parse failed (%s), using fallback.", exc)
            return self._fallback(raw)

    def _normalize(self, data: dict, raw: str) -> dict:
        """
        Normalise the parsed JSON using ONLY the fields declared in output_schema.
        Type coercions are applied based on the type hint string.
        Unknown/extra fields from the LLM are silently dropped.
        """
        result: dict = {}
        for field, type_hint in self._output_fields.items():
            raw_value = data.get(field)
            result[field] = self._coerce(field, raw_value, str(type_hint), raw)
        return result

    @staticmethod
    def _coerce(field: str, value: Any, type_hint: str, raw: str) -> Any:
        """
        Best-effort type coercion based on the hint string.

        Float clamping: applied to ALL float fields (LLM confidence values
        must always be in [0, 1]).  If a float field genuinely needs to exceed
        this range, declare it with type hint "float_unbounded".
        """
        hint = type_hint.lower().split("#")[0].strip()   # strip inline comments

        if value is None:
            # Sensible defaults per type
            if "bool" in hint:
                return False
            if "float" in hint or "int" in hint:
                return 0.0
            return ""

        try:
            if "bool" in hint:
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "1", "yes")
            if "float" in hint and "unbounded" not in hint:
                v = float(value)
                # Always clamp to [0, 1] for bounded floats (e.g. confidence, score)
                return round(max(0.0, min(1.0, v)), 3)
            if "float" in hint:
                return round(float(value), 3)
            if "int" in hint:
                return int(value)
            # string / default
            return str(value)
        except (TypeError, ValueError):
            logger.warning("Coerce failed for field '%s' (hint=%s), using raw fallback.", field, hint)
            return str(raw)[:200]

    @staticmethod
    def _extract_json(text: str) -> str:
        """
        Extract the first complete JSON object from *text*.

        Strategy (in order):
          1. Fenced code block  ```json { ... } ```
          2. Bracket-balanced scan — finds the '{' that opens the outermost
             object and walks forward counting braces, handling strings and
             escape sequences.  This correctly handles nested objects and
             braces inside string values.
          3. Simple first-{/last-} slice (legacy fallback).
        """
        # Strategy 1: fenced block
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)

        # Strategy 2: bracket-balanced scan
        start = text.find("{")
        if start != -1:
            depth = 0
            in_string = False
            escape_next = False
            for i, ch in enumerate(text[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\" and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start: i + 1]

        # Strategy 3: legacy fallback
        end = text.rfind("}")
        if start != -1 and end != -1 and start < end:
            return text[start: end + 1]

        return text

    def _fallback(self, raw: str) -> dict:
        """
        Return a zeroed-out result matching the spec's output_schema.

        Raw LLM text is injected ONLY into fields whose names are reason-like
        (reason, explanation, message, detail, rationale, summary).
        Other string fields are left as empty strings to avoid polluting
        decision / category fields with raw model output.
        """
        result: dict = {}
        for field, type_hint in self._output_fields.items():
            result[field] = self._coerce(field, None, str(type_hint), raw)

        # Inject raw text into the first reason-like string field only
        for field, type_hint in self._output_fields.items():
            if (
                field.lower() in _REASON_LIKE_FIELDS
                and "str" in str(type_hint).lower()
                and not result.get(field)
            ):
                result[field] = str(raw)[:200]
                break

        return result

    def _error_result(self, msg: str) -> dict:
        """
        Return a schema-compliant zeroed result annotated with the error message.
        Uses the output_schema so the structure is always consistent with normal
        results, regardless of which task is being evaluated.
        """
        result: dict = {}
        for field, type_hint in self._output_fields.items():
            result[field] = self._coerce(field, None, str(type_hint), msg)

        # Inject error message into the first reason-like string field
        for field, type_hint in self._output_fields.items():
            if (
                field.lower() in _REASON_LIKE_FIELDS
                and "str" in str(type_hint).lower()
            ):
                result[field] = f"llm_error: {msg}"[:200]
                break

        logger.error("Returning error result for task '%s': %s", self.task_name, msg)
        return result
