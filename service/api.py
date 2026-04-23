from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter()

_pipeline = None


def set_pipeline(pipeline):
    global _pipeline
    _pipeline = pipeline


# ===== 请求结构 =====
class EvaluateRequest(BaseModel):
    # New generic fields
    task: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

    # Legacy field — still accepted for backward compatibility
    ticket: Optional[str] = None

    # Extra metadata (passed into context transparently)
    meta: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def resolve_context(self) -> "EvaluateRequest":
        """
        Ensure there is always a usable context dict.
        Priority: explicit `context` > legacy `ticket` string.
        """
        if not self.context:
            if self.ticket:
                self.context = {"content": self.ticket}
            else:
                raise ValueError("Provide either 'context' (dict) or 'ticket' (str).")
        if self.meta:
            self.context.update(self.meta)
        return self


# ===== 健康检查 =====
@router.get("/health")
def health():
    return {"status": "ok"}


# ===== 核心评估接口 =====
@router.post("/mtrust/evaluate")
def evaluate(req: EvaluateRequest):
    if _pipeline is None:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    start_time = time.time()

    try:
        task = req.task  # None → pipeline uses DEFAULT_TASK
        logger.info("[MTrust] task=%s context_keys=%s", task, list((req.context or {}).keys()))

        result = _pipeline.run(req.context, task=task)

        duration = round(time.time() - start_time, 4)
        logger.info("[MTrust] result=%s", result)

        return {
            "code": 0,
            "message": "success",
            "data": result,
            "cost_time": duration,
        }

    except Exception as e:
        logger.error("[MTrust] error=%s", str(e))
        raise HTTPException(status_code=500, detail=str(e))