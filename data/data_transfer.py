import pandas as pd
import json
from collections import Counter

# ===== 配置 =====
INPUT_FILE = "样例.xlsx"
OUTPUT_FILE = "cases_core.json"

# ===== 读取Excel =====
df = pd.read_excel(INPUT_FILE)
df = df.fillna("")  # 防止NaN

result = []

for idx, row in df.iterrows():
    try:
        # ===== ❻ 过滤无效数据 =====
        if str(row.get("有效数据", "")).strip() == "否":
            continue

        # ===== 字段读取 =====
        content = str(row.get("元数据基本信息", "")).strip()
        audit_result = str(row.get("第一次稽核服务稽核结果", "")).strip()
        score_raw = str(row.get("总得分（第一次）", "")).strip()
        expert_result = str(row.get("第一次专家审核结果", "")).strip()

        # ===== score标准化 =====
        try:
            score = str(int(float(score_raw)))
        except:
            score = "0"

        # ===== label =====
        label = "correct" if score == "100" else "incorrect"

        # ===== error_type（带优先级 + label约束）=====
        if label == "correct":
            error_type = "none"
        else:
            if "上传文件失败" in audit_result:
                error_type = "upload_error"
            elif expert_result.lower() == "zip":
                error_type = "zip_error"
            else:
                error_type = "model_error"

        # ===== 组装 =====
        result.append({
            "content": content,
            "audit_result": audit_result,
            "label": label,
            "score": score,
            "error_type": error_type
        })

    except Exception as e:
        print(f"[ERROR] 第 {idx} 行处理失败：{e}")
        continue

# ===== 保存 =====
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# ===== 统计 =====
error_counter = Counter([x["error_type"] for x in result])
label_counter = Counter([x["label"] for x in result])

print(f"✅ 转换完成，共 {len(result)} 条")
print("📊 label分布:", label_counter)
print("📊 error_type分布:", error_counter)