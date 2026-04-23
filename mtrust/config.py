# -*- coding: utf-8 -*-
import os
from .generation_mode import GenerationMode

def str2bool(x) -> bool:
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    return str(x).strip().lower() in {"1", "true", "yes", "y", "on"}

# 模型路径与推理参数
MODEL_PATH = os.environ.get("MODEL_PATH", "./Qwen2.5-little-sparrow")

# dtype 自动选择
DTYPE = None


# 生成参数（统一管理）
new_gen_tokens = 3072
GEN_KW = dict(
    # 用于transformers & outlines
    max_new_tokens=new_gen_tokens,

    # 用于OPENAI调用规范
    max_tokens=new_gen_tokens,

    temperature=0.1,
    top_p=0.1,
    stream = str(os.environ.get("OPENAI_IS_STREAM", "false")).lower() in ("1", "true", "yes"),
    logprobs = str(os.environ.get("OPENAI_LOGPROBS", "false")).lower() in ("1", "true", "yes")
)

# Gradio
SERVER_NAME = "0.0.0.0"
SERVER_PORT = int(os.environ.get("PORT", 8006))


# OpenAI 配置
OPENAI_IS_STREAM = str2bool(os.environ.get("OPENAI_IS_STREAM", "FALSE"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-f50d069cabff4407be17dae27ca461b7")
OPENAI_API_BASE_URL = os.environ.get("OPENAI_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
OPENAI_MODEL_NAME = os.environ.get("OPENAI_MODEL_NAME", "qwq-32b")  
OPENAI_EMBEDDING_MODEL_NAME = os.environ.get("OPENAI_EMBEDDING_MODEL_NAME", "text-embedding-v4")

# PANZHI 配置
PZ_BASE_URL = os.environ.get("PZ_BASE_URL", "http://172.21.153.46:9050/gw/v1/")
PZ_API_KEY = os.environ.get("PZ_API_KEY", "sk-placeholder")
PZ_MODEL_NAME = os.environ.get("PZ_MODEL_NAME", "Qwen3-32B(100k)")
PZ_Path = os.environ.get("PZ_Path", "/gw/v1")
TDEV = os.environ.get("TDEV", 0)
APPID = os.environ.get("APPID", "xiaotong")
APPKEY = os.environ.get("APPKEY", "6bee93448696a143e28bfb49834808ec")
PANZHI_IS_STREAM = str2bool(os.environ.get("PANZHI_IS_STREAM", "FALSE"))

# 生成模式（用于 LLM 调用）— 可通过环境变量配置
# 允许的值：CONSTRAINED, DIRECT, OPENAI
g_mode = GenerationMode[os.environ.get("GENERATION_MODE", "OPENAI").upper()]
