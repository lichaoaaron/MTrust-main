# -*- coding: utf-8 -*-
"""
DeepEval Adapter  (backward-compatibility shim)
================================================
This class is kept so that existing callers are not broken.
Internally it delegates to SpecEvaluator with the audit_false_positive task.
"""
from mtrust.evaluators.spec_evaluator import SpecEvaluator


class DeepEvalAdapter:
    """Legacy wrapper — prefer SpecEvaluator("audit_false_positive") directly."""

    def __init__(self):
        self._evaluator = SpecEvaluator("audit_false_positive")

    def evaluate(self, ticket: dict) -> dict:
        return self._evaluator.evaluate(ticket)
