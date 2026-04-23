import json
import re

# ================================
# 配置：评分规则（最终唯一来源）
# ================================
SCORE_MAP = {
    "HIGH": 100,
    "MEDIUM": 100,
    "LOW": 5
}

# ================================
# 提取风险段落（更稳）
# ================================
def extract_section(text, section_name):
    pattern = rf"{section_name}问题\*\*(.*?)(?=\n\*\*（|$)"
    match = re.search(pattern, text, re.S)
    if not match:
        return ""
    return match.group(1).strip()

# ================================
# 解析风险块
# ================================
def parse_risk_block(block_text, risk_level):
    risks = []

    if not block_text or "（无）" in block_text:
        return risks

    parts = re.split(r"- 问题\d+", block_text)

    for idx, part in enumerate(parts[1:], start=1):
        part = part.strip()

        # label识别
        if "(label-错误)" in part or "（label-错误）" in part:
            label = "incorrect"
            part = re.sub(r"[（(]label-错误[）)]", "", part)
        else:
            label = "correct"

        part = part.lstrip("：:").strip()

        prefix = {
            "HIGH": "H",
            "MEDIUM": "M",
            "LOW": "L"
        }[risk_level]

        risk_id = f"{prefix}_{idx}"

        risks.append({
            "risk_id": risk_id,
            "risk_message": part,
            "risk_level": risk_level,
            "label": label
        })

    return risks

# ================================
# 解析 audit_result
# ================================
def parse_audit_result(audit_result):
    risks = []
    risks += parse_risk_block(extract_section(audit_result, "高风险"), "HIGH")
    risks += parse_risk_block(extract_section(audit_result, "中风险"), "MEDIUM")
    risks += parse_risk_block(extract_section(audit_result, "低风险"), "LOW")
    return risks

# ================================
# 评分函数（强化版：显式一票否决 + debug）
# ================================
def calc_score(risks, debug=False):
    score = 100

    for r in risks:
        if r["label"] != "incorrect":
            continue

        level = r["risk_level"]

        # ⭐ 一票否决（核心）
        if level in ["HIGH", "MEDIUM"]:
            if debug:
                print(f"[KILL] {r['risk_id']} ({level}) → score=0")
            return 0

        # ⭐ 低风险扣分
        if level == "LOW":
            score -= SCORE_MAP["LOW"]
            if debug:
                print(f"[LOW] {r['risk_id']} → -5")

    final_score = max(score, 0)

    if debug:
        print(f"[FINAL SCORE] {final_score}")

    return final_score

# ================================
# 主转换函数（强制打印校验）
# ================================
def convert_cases(input_path, output_path, debug=False):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    new_data = []

    for i, case in enumerate(data):
        risks = parse_audit_result(case["audit_result"])
        new_score = calc_score(risks, debug=debug)

        if debug:
            print(f"\n===== CASE {i} =====")
            print("score:", new_score)

        new_case = {
            "content": case["content"],
            "risks": risks,
            "meta": {
                "score": new_score,
                "error_type": case.get("error_type", "unknown")
            }
        }

        new_data.append(new_case)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ DONE: saved to {output_path}")

# ================================
# 执行
# ================================
if __name__ == "__main__":
    convert_cases(
        "data/cases.json",
        "data/cases_risk_level.json",
        debug=True   # ⭐ 强烈建议先开着
    )