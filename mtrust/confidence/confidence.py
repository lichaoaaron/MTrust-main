# -*- coding: utf-8 -*-
"""
Confidence Model
================
Task-agnostic confidence calibration, driven by confidence_model.yaml.

Supported calibration methods:
    weighted_average  — (default) linear blend of model confidence + evidence strength
    self_consistency  — call LLM N times, use agreement rate (future)

Config keys read from YAML (all optional, defaults shown):
    method             : weighted_average
    confidence_field   : confidence   # name of the confidence field in eval_result
    reason_field       : reason       # name of the reason/explanation field
    weights:
      model_conf       : 0.7
      evidence         : 0.3
    threshold          : 0.5   # minimum calibrated confidence to be considered "positive"
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "specs" / "03_confidence" / "confidence_model.yaml"


class ConfidenceModel:

    def __init__(self, config_path: str | Path | None = None):
        path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                cfg: dict = yaml.safe_load(f) or {}
        else:
            logger.warning("confidence_model.yaml not found at %s, using defaults.", path)
            cfg = {}

        self._method: str = cfg.get("method", "weighted_average")

        # Configurable field names — allows tasks to use "score", "explanation", etc.
        self._confidence_field: str = cfg.get("confidence_field", "confidence")
        self._reason_field: str     = cfg.get("reason_field", "reason")

        weights = cfg.get("weights") or {}
        self._w_model: float    = float(weights.get("model_conf", 0.7))
        self._w_evidence: float = float(weights.get("evidence",   0.3))

        # Normalise so weights always sum to 1.0
        total = self._w_model + self._w_evidence
        if total > 0:
            self._w_model    /= total
            self._w_evidence /= total

        self._threshold: float = float(cfg.get("threshold", 0.5))

        logger.debug(
            "ConfidenceModel loaded: method=%s conf_field=%s reason_field=%s "
            "w_model=%.2f w_evidence=%.2f threshold=%.2f",
            self._method, self._confidence_field, self._reason_field,
            self._w_model, self._w_evidence, self._threshold,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def compute(self, eval_result: dict) -> dict:
        """
        Calibrate confidence and pass all other fields through unchanged.
        Only the confidence field (configurable) is replaced; all other
        task-specific fields are never touched.
        """
        base_conf = self._to_float(eval_result.get(self._confidence_field, 0.5))
        reason    = str(eval_result.get(self._reason_field, ""))

        if not eval_result.get(self._confidence_field):
            logger.warning(
                "ConfidenceModel: field '%s' not found in eval_result (keys: %s). "
                "Using default 0.5. Check that confidence_field in confidence_model.yaml "
                "matches the output_schema field name in the task spec.",
                self._confidence_field,
                list(eval_result.keys()),
            )

        if self._method == "self_consistency":
            # Placeholder: self-consistency requires LLM re-calls from the
            # pipeline layer.  Fall back to weighted_average until implemented.
            logger.debug("self_consistency not yet implemented, falling back to weighted_average.")
            calibrated = self._weighted_average(base_conf, reason)
        else:
            calibrated = self._weighted_average(base_conf, reason)

        result = dict(eval_result)
        result[self._confidence_field] = calibrated
        logger.debug(
            "ConfidenceModel.compute: base=%.3f → calibrated=%.3f (threshold=%.3f)",
            base_conf, calibrated, self._threshold,
        )
        return result

    # ------------------------------------------------------------------ #
    # Calibration strategies
    # ------------------------------------------------------------------ #

    def _weighted_average(self, base_conf: float, reason: str) -> float:
        evidence_score = self._evidence_strength(reason)
        raw = self._w_model * base_conf + self._w_evidence * evidence_score
        return round(max(0.0, min(1.0, raw)), 3)

    # ------------------------------------------------------------------ #
    # Evidence strength — task-agnostic heuristic
    # ------------------------------------------------------------------ #

    @staticmethod
    def _evidence_strength(text: str) -> float:
        """
        Score 0.0–1.0 based on the *richness and specificity* of the reason text.

        Signals used (all task-agnostic):
          - Word count         : more words → richer explanation
          - Numeric presence   : numbers/dates/percentages → concrete evidence
          - Paired quotes      : text in paired double-quotes → direct citation
            (single quotes are intentionally excluded to avoid false positives
             from contractions like "it's", "don't" in natural language text)

        Deliberately avoids domain keywords so it works across all tasks.
        """
        if not text:
            return 0.2

        words = text.split()
        word_count = len(words)

        # Base score from word count
        if word_count >= 25:
            base = 0.8
        elif word_count >= 12:
            base = 0.65
        elif word_count >= 5:
            base = 0.45
        else:
            base = 0.25

        bonus = 0.0

        # +0.1 if contains any numeric token (dates, percentages, counts)
        if any(any(c.isdigit() for c in w) for w in words):
            bonus += 0.1

        # +0.1 if contains paired double-quotes (direct citation of evidence)
        # Uses only double-quote variants; single quotes are excluded because
        # English contractions (it's, don't) would trigger this almost always.
        double_quote_count = text.count('"') + text.count('\u201c') + text.count('\u201d')
        if double_quote_count >= 2:
            bonus += 0.1

        return round(min(1.0, base + bonus), 3)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_float(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5