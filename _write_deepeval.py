lines = [
    "# -*- coding: utf-8 -*-\n",
    '"""\n',
    "DeepEval Adapter  (backward-compatibility shim)\n",
    "================================================\n",
    "This class is kept so that existing callers are not broken.\n",
    "Internally it delegates to SpecEvaluator with the audit_false_positive task.\n",
    '"""\n',
    "from mtrust.evaluators.spec_evaluator import SpecEvaluator\n",
    "\n",
    "\n",
    "class DeepEvalAdapter:\n",
    '    """Legacy wrapper — prefer SpecEvaluator("audit_false_positive") directly."""\n',
    "\n",
    "    def __init__(self):\n",
    '        self._evaluator = SpecEvaluator("audit_false_positive")\n',
    "\n",
    "    def evaluate(self, ticket: dict) -> dict:\n",
    "        return self._evaluator.evaluate(ticket)\n",
]

with open(r"mtrust\evaluators\deepeval_adapter.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Written deepeval_adapter.py")
