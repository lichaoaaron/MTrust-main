from typing import Dict, Any, List, Optional, Type, get_origin, get_args
from enum import Enum
from pydantic import BaseModel, Field, create_model, ValidationError
from typing import Optional, Union, get_origin, get_args
import enum
import re
import datetime
import hashlib


def text_to_seed(text: str, bits: int = 31) -> int:
    """把文本映射到 0 ~ 2**bits-1 的整数，用于 seed。同一段文本在任何机器 / 任何进程里结果都一样（稳定）；bits不能超过64"""
    h = hashlib.blake2b(text.encode("utf-8"), digest_size=8)
    v64 = int.from_bytes(h.digest(), "big", signed=False)
    mask = (1 << bits) - 1
    return v64 & mask


def get_inner_type(tp):
    """递归获取 Optional 或 Union 中的真实类型, Optional[T]等价于Union[T, None]"""
    origin = get_origin(tp)
    if origin in (Union, Optional):
        args = get_args(tp)
        # 找到第一个非 None 的参数
        for arg in args:
            if arg is not type(None):  # noqa
                return get_inner_type(arg)  # 继续展开
    return tp

def parse_dt(v):
    """尝试将数据解析为 datetime 对象，支持多种常见格式"""
    if isinstance(v, datetime.datetime): 
        return v
    
    if not v: 
        return None
    
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(str(v), fmt)
        except: continue

    return None

def get_path_value(data: Dict, path: str):
    """根据点分隔路径获取嵌套字典中的值，找不到则返回None"""
    keys = path.split('.')
    val = data
    for key in keys:
        if isinstance(val, dict): val = val.get(key)
        else: return None
    return val

_placeholder_pattern = re.compile(r"\{([^{}]+)\}")
def fill_template(template: str, data: Dict[str, Any]) -> str:
    """
    格式化违规消息，支持从多个地方获取路径
    """
    def replace(match: re.Match) -> str:
        """输入为 {path}，输出为对应的值，如： {llm_info.security_approval_date}"""
        path = match.group(1).strip()

        value = get_path_value(data, path)
        if value is None:
            # 找不到就返回空字符串
            return ""
        
        # 转成字符串再塞进去
        return str(value)

    return _placeholder_pattern.sub(replace, template)


def show_pydantic_model_schema(obj: Type[BaseModel]):
    """
    打印出 Pydantic 对象的详细结构说明。
    """
    if not obj:
        print("没有定义任何需要LLM提取的字段，提取模型为空。")
        return

    # 在Pydantic V2中，推荐使用 .model_fields
    fields_to_inspect = obj.model_fields

    print("\n" + "="*50)
    print(f"动态提取模型 '{obj.__name__}' 结构说明")
    print("="*50)

    for field_name, model_field in fields_to_inspect.items():
        print(f"\n字段名称 (Field Name): {field_name}")
        print(f"  - 描述 (Description): {model_field.description}")
        
        # 使用 .annotation 替代 .outer_type_
        print(f"  - 数据类型 (Type): {model_field.annotation}")
        
        print(f"  - 初始值 (Default): {model_field.default}")

        # 更健壮的枚举检查方式
        field_type = model_field.annotation
        # 处理 Optional[Enum]、List[Enum] 的情况
        origin_type = get_origin(field_type)
        if origin_type is Optional or origin_type is list:
            inner_type = get_args(field_type)[0]
            if isinstance(inner_type, type) and issubclass(inner_type, Enum):
                enum_values = [member.value for member in inner_type]
                print(f"  - 合法枚举值 (Enum Values): {enum_values}")
        # 处理直接是 Enum 的情况
        elif isinstance(field_type, type) and issubclass(field_type, Enum):
            enum_values = [member.value for member in field_type]
            print(f"  - 合法枚举值 (Enum Values): {enum_values}")

    print("\n" + "="*50)


def iter_json_paths(obj, prefix=""):
    """
    深度优先遍历JSON对象，逐个yield路径
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_prefix = f"{prefix}.{k}" if prefix else k
            yield from iter_json_paths(v, new_prefix)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            new_prefix = f"{prefix}[{idx}]"
            yield from iter_json_paths(item, new_prefix)
    else:
        # 到达叶子节点，返回路径
        yield prefix

def _json_default(o):
    if isinstance(o, datetime.datetime):
        return o.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(o, datetime.date):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, enum.Enum):
        return o.value
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


if __name__ == "__main__":
    inner_type = get_inner_type(Optional[int])
    print(f"inner_type of Optional[int]: {inner_type}")

    inner_type = get_inner_type(Optional[List[int]])
    print(f"inner_type of Optional[List[int]]: {inner_type}")   

    # JSON路径遍历示例
    data = {
        "a": {"b": {"c": 1}, "d": 2},
        "e": 3,
        "f": [{"x": 1}, {"y": 2}]
    }
    result = iter_json_paths(data)
    for p in result:
        print(p)