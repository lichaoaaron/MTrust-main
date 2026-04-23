from enum import Enum

class GenerationMode(Enum):
    """定义LLM服务的生成模式。"""
    CONSTRAINED = "constrained"
    DIRECT = "direct"
    OPENAI = "openai"
    PANZHI = "panzhi"