import logging
from mtrust.signals.signal_detector import SignalDetector
from mtrust.evaluators.spec_evaluator import SpecEvaluator
from mtrust.loader.spec_loader import SpecLoader
from mtrust.confidence.confidence import ConfidenceModel
from mtrust.policy.trigger_engine import TriggerEngine


logger = logging.getLogger(__name__)


class MTrustPipeline:
    """
    Spec-driven, task-agnostic evaluation pipeline.

    Usage (default audit task — backward compatible):
        pipeline = MTrustPipeline(spec_root)
        result   = pipeline.run(ticket)

    Usage (explicit task):
        result = pipeline.run(context_dict, task="qa_correctness")
    """

    DEFAULT_TASK = "audit_confidence"

    # Threshold below which audit result is considered unreliable / intercepted
    INTERCEPT_THRESHOLD = 0.6

    def __init__(self, spec_root):
        loader = SpecLoader(spec_root)

        self.signal_config = loader.load_yaml("02_signal/signals.yaml")
        self.policy = loader.load_yaml("04_policy/trigger_policy.yaml")

        self.signal_detector = SignalDetector(self.signal_config)
        self.trigger_engine = TriggerEngine(self.policy)
        self.confidence_model = ConfidenceModel()

        # Cache SpecEvaluator instances by task name to avoid repeated YAML I/O
        # on every pipeline.run() call (important for batch / API scenarios).
        self._evaluator_cache: dict[str, SpecEvaluator] = {}

    def _get_evaluator(self, task: str) -> SpecEvaluator:
        if task not in self._evaluator_cache:
            logger.debug("SpecEvaluator cache miss — loading spec for task '%s'", task)
            self._evaluator_cache[task] = SpecEvaluator(task)
        return self._evaluator_cache[task]

    def run(self, ticket, task: str | None = None) -> dict:
        task = task or self.DEFAULT_TASK

        # ── 1. Build context ──────────────────────────────────────────────
        context: dict = ticket.copy() if isinstance(ticket, dict) else {"content": str(ticket)}
        context.setdefault("ticket", context.get("content", ""))

        # ── 2. Signal detection ───────────────────────────────────────────
        text = context.get("content", "")
        context["signals"] = self.signal_detector.detect(text)

        # ── 3. Spec-driven evaluation (single LLM entry point) ────────────
        evaluator = self._get_evaluator(task)
        eval_result = evaluator.evaluate(context)

        # ── 4. Confidence calibration (no LLM, task-agnostic) ─────────────
        final = self.confidence_model.compute(eval_result)

        # ── 5. Output — pass all eval fields through; add pipeline metadata ─
        confidence_field = self.confidence_model._confidence_field
        calibrated_conf = final.get(confidence_field, 0.0)

        # Threshold decision: intercepted when confidence is below threshold
        intercepted = calibrated_conf < self.INTERCEPT_THRESHOLD

        return {
            "task": task,
            "confidence": calibrated_conf,
            "confidence_level": final.get("overall_confidence_level", ""),
            "intercepted": intercepted,
            "risk": self._confidence_to_risk(calibrated_conf),
            "detail": {k: v for k, v in final.items()
                       if k not in (confidence_field, "overall_confidence_level")},
        }

    @staticmethod
    def _confidence_to_risk(confidence: float) -> str:
        """Map calibrated confidence to risk label (mirrors confidence band definition)."""
        if confidence >= 0.9:
            return "可用"
        if confidence >= 0.6:
            return "需确认"
        if confidence >= 0.3:
            return "高风险"
        return "不可用"