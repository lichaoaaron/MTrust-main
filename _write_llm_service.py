content = (
    "# -*- coding: utf-8 -*-\n"
    '"""\n'
    "LLM Service\n"
    "===========\n"
    "Single responsibility: call the LLM with a fully-formed prompt string and\n"
    "return the raw text response.  No prompt construction lives here.\n"
    '"""\n'
    "import os\n"
    "import logging\n"
    "from openai import OpenAI\n"
    "from dotenv import load_dotenv\n"
    "\n"
    "load_dotenv()\n"
    "\n"
    "logger = logging.getLogger(__name__)\n"
    "\n"
    "# ==================== 环境变量读取 ====================\n"
    'OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL")\n'
    'OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")\n'
    'OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "qwen-flash")\n'
    "\n"
    'TEMPERATURE = float(os.getenv("CONFIDENCE_TEMPERATURE", 0.1))\n'
    'MAX_TOKENS = int(os.getenv("CONFIDENCE_MAX_TOKENS", 1024))\n'
    "\n"
    "# ==================== 初始化客户端 ====================\n"
    "client = OpenAI(\n"
    "    api_key=OPENAI_API_KEY,\n"
    "    base_url=OPENAI_API_BASE_URL\n"
    ")\n"
    "\n"
    "\n"
    "# ==================== 核心调用 ====================\n"
    "def call_llm(prompt: str) -> str:\n"
    '    """\n'
    "    Call the configured LLM with *prompt* and return the raw text response.\n"
    "    Raises on hard errors so callers can handle fallback logic themselves.\n"
    '    """\n'
    '    logger.debug("Calling LLM (model=%s, max_tokens=%s)", OPENAI_MODEL_NAME, MAX_TOKENS)\n'
    "    resp = client.chat.completions.create(\n"
    "        model=OPENAI_MODEL_NAME,\n"
    '        messages=[{"role": "user", "content": prompt}],\n'
    "        temperature=TEMPERATURE,\n"
    "        max_tokens=MAX_TOKENS,\n"
    "    )\n"
    "    text = resp.choices[0].message.content\n"
    '    logger.debug("LLM raw response: %s", text[:200])\n'
    "    return text\n"
)

with open(r"mtrust\llm_service.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Written successfully.")
