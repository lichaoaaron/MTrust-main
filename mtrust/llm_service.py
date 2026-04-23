# -*- coding: utf-8 -*-
"""
LLM Service
===========
Single responsibility: call the LLM with a fully-formed prompt string and
return the raw text response.  No prompt construction lives here.
"""
import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ==================== 环境变量读取 ====================
OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "qwen-flash")

TEMPERATURE = float(os.getenv("CONFIDENCE_TEMPERATURE", 0.1))
MAX_TOKENS = int(os.getenv("CONFIDENCE_MAX_TOKENS", 1024))

# ==================== 初始化客户端 ====================
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_API_BASE_URL
)


# ==================== 核心调用 ====================
def call_llm(prompt: str, system_prompt: str | None = None) -> str:
    """
    Call the configured LLM and return the raw text response.

    Args:
        prompt        : The user-turn message (input context + output request).
        system_prompt : Optional system-role instruction (task definition,
                        persona, output rules).  When provided it is sent as a
                        separate system message, which models treat with higher
                        authority than user messages.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    logger.debug(
        "Calling LLM (model=%s, roles=%s)",
        OPENAI_MODEL_NAME,
        [m["role"] for m in messages],
    )
    resp = client.chat.completions.create(
        model=OPENAI_MODEL_NAME,
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    text: str = resp.choices[0].message.content or ""
    logger.debug("LLM raw response: %s", text[:200])
    return text
