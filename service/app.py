from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import time

from service.api import router, set_pipeline
from mtrust.pipeline.pipeline import MTrustPipeline

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    logger.info("🚀 Initializing MTrustPipeline...")

    start = time.time()
    pipeline = MTrustPipeline(spec_root="mtrust/specs")
    set_pipeline(pipeline)

    logger.info(f"✅ Pipeline initialized in {time.time() - start:.2f}s")
    yield
    logger.info("🛑 Shutting down MTrust service...")


app = FastAPI(
    title="MTrust Service",
    description="LLM Confidence & Risk Evaluation Service",
    version="1.0.0",
    lifespan=lifespan
)

# 注册路由
app.include_router(router)