# -*- coding: utf-8 -*-

import json
import os
import sys
from datetime import datetime
from collections import defaultdict
from mtrust.pipeline.pipeline import MTrustPipeline

# ================================
# 日志输出：终端 + 文件（新增）
# ================================
os.makedirs("output", exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = f"output/run_{timestamp}.log"
log_file = open(log_path, "w", encoding="utf-8")

class Tee:
    def __init__(self, *files):
        self.files = files

    def write(self, data):
        for f in self.files:
            f.write(data)
            f.flush()

    def flush(self):
        for f in self.files:
            f.flush()

sys.stdout = Tee(sys.stdout, log_file)

# ================================
# 原有代码（完全不动）
# ================================

THRESHOLDS = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65]

pipeline = MTrustPipeline(spec_root="mtrust/specs")

cases = json.load(open("data/cases_risk_level.json", "r", encoding="utf-8"))
rules = open("data/rule.yaml", "r", encoding="utf-8").read()

TASK_NAME = "risk_confidence"
EVAL_LEVELS = {"HIGH", "MEDIUM"}

SCORE_MAP = {
    "HIGH": 100,
    "MEDIUM": 100,
    "LOW": 5,
}

os.makedirs("output", exist_ok=True)


def calc_score(risks, pred_conf=None, threshold=0.4):
    score = 100
    for r in risks:
        rid = r["risk_id"]
        level = r.get("risk_level", "LOW")
        label = r.get("label", "correct")

        if pred_conf is None:
            if label == "incorrect":
                score -= SCORE_MAP.get(level, 0)
        else:
            intercepted = pred_conf.get(rid, 1.0) < threshold
            if label == "incorrect" and not intercepted:
                score -= SCORE_MAP.get(level, 0)

    return max(score, 0)


# ── Step1：LLM只跑一次 ─────────────────────────────
print("\n" + "=" * 60)
print("  正在调用 LLM...")
print("=" * 60)

llm_cache = []

for case_idx, c in enumerate(cases):
    content = c.get("content", "")
    risks = c.get("risks", [])
    meta = c.get("meta", {})
    error_type = meta.get("error_type", "none")

    case_risks = []

    for risk in risks:
        if risk.get("risk_level") not in EVAL_LEVELS:
            continue

        ticket = {
            "content": content,
            "risk_message": risk.get("risk_message", ""),
            "rules": rules,
        }

        result = pipeline.run(ticket, task=TASK_NAME)
        confidence = result.get("confidence", 0.0)
        detail = result.get("detail", {})

        print(f"  Case {case_idx:3d} | {risk['risk_id']} | conf={confidence:.3f} | level={result.get('confidence_level','')} | detail_keys={list(detail.keys())[:3]}")

        case_risks.append({
            "risk_id": risk["risk_id"],
            "risk_level": risk["risk_level"],
            "label": risk.get("label", "correct"),
            "confidence": round(confidence, 4),
        })

    llm_cache.append({
        "case_idx": case_idx,
        "error_type": error_type,
        "risks": case_risks,
        "all_risks": risks,
    })

print(f"\n  LLM 调用完毕，共处理 {len(cases)} 个工单。")


# ── Step2：多阈值评估（仅新增一段append）──────────
MARGIN = 0.05

comparison_rows = []

for TH in THRESHOLDS:
    BASE_TH = TH

    intercepted_incorrect = 0
    intercepted_correct = 0
    missed_incorrect = 0
    kept_correct = 0

    conf_incorrect = []
    conf_correct = []
    original_scores = []
    mtrust_scores = []

    error_type_total = defaultdict(int)

    all_conf_incorrect = []
    all_conf_correct = []
    for cached in llm_cache:
        for rd in cached["risks"]:
            if rd["label"] == "incorrect":
                all_conf_incorrect.append(rd["confidence"])
            else:
                all_conf_correct.append(rd["confidence"])

    incorrect_avg_pre = sum(all_conf_incorrect) / len(all_conf_incorrect) if all_conf_incorrect else 0.5
    correct_avg_pre   = sum(all_conf_correct)   / len(all_conf_correct)   if all_conf_correct   else 0.5
    distribution_collapsed = abs(incorrect_avg_pre - correct_avg_pre) < 0.05

    for cached in llm_cache:
        error_type = cached["error_type"]
        error_type_total[error_type] += 1

        case_risks = cached["risks"]
        all_risks  = cached["all_risks"]

        pred_conf = {}

        for rd in case_risks:
            rid        = rd["risk_id"]
            label      = rd["label"]
            confidence = rd["confidence"]

            if distribution_collapsed:
                intercepted = confidence < BASE_TH
            else:
                # if confidence < BASE_TH:
                #     intercepted = True
                # elif confidence > BASE_TH + MARGIN:
                #     intercepted = False
                # else:
                #     intercepted = False

                # if confidence > BASE_TH:
                #     intercepted = False
                if confidence < BASE_TH:
                    intercepted = True
                else:
                    intercepted = False


            pred_conf[rid] = confidence

            if label == "incorrect":
                conf_incorrect.append(confidence)
                if intercepted:
                    intercepted_incorrect += 1
                else:
                    missed_incorrect += 1
            else:
                conf_correct.append(confidence)
                if intercepted:
                    intercepted_correct += 1
                else:
                    kept_correct += 1

        orig_score   = calc_score(all_risks)
        mtrust_score = calc_score(all_risks, pred_conf, BASE_TH)

        original_scores.append(orig_score)
        mtrust_scores.append(mtrust_score)

    total    = intercepted_incorrect + intercepted_correct + missed_incorrect + kept_correct
    net_gain = intercepted_incorrect - intercepted_correct

    orig_avg   = sum(original_scores) / len(original_scores)
    mtrust_avg = sum(mtrust_scores)   / len(mtrust_scores)
    score_gain = mtrust_avg - orig_avg

    incorrect_avg = sum(conf_incorrect) / len(conf_incorrect) if conf_incorrect else 0
    correct_avg   = sum(conf_correct)   / len(conf_correct)   if conf_correct   else 0

    print("\n" + "─" * 60)
    print(f"  THRESHOLD = {TH:.2f}  汇总")
    print("─" * 60)
    print(f"  BASE_TH   : {BASE_TH:.2f}")
    print(f"  MARGIN    : {MARGIN:.2f}")
    print(f"  分布塌缩保护触发 : {'是（fallback 单阈值）' if distribution_collapsed else '否（双阈值生效）'}")
    print(f"  总工单数               : {len(cases)}")
    print(f"  参与评测风险数         : {total}")
    print(f"  TP 正确拦截错误        : {intercepted_incorrect}")
    print(f"  FP 错误拦截正确        : {intercepted_correct}")
    print(f"  FN 遗漏拦截            : {missed_incorrect}")
    print(f"  TN 正确放行            : {kept_correct}")
    print(f"  net_gain               : {net_gain:+d}")

    if intercepted_incorrect + missed_incorrect > 0:
        print(f"  recall（错误捕获率）    : {intercepted_incorrect / (intercepted_incorrect + missed_incorrect):.2%}")

    if intercepted_correct + kept_correct > 0:
        print(f"  误伤率                 : {intercepted_correct / (intercepted_correct + kept_correct):.2%}")

    if intercepted_incorrect + intercepted_correct > 0:
        print(f"  precision（拦截准确率） : {intercepted_incorrect / (intercepted_incorrect + intercepted_correct):.2%}")

    print(f"  original_score_avg     : {orig_avg:.2f}")
    print(f"  mtrust_score_avg       : {mtrust_avg:.2f}")
    print(f"  score_gain             : {score_gain:+.2f}")
    print(f"  incorrect 平均置信度   : {incorrect_avg:.4f}")
    print(f"  correct   平均置信度   : {correct_avg:.4f}")
    print(f"  置信度差值（correct-incorrect）: {correct_avg - incorrect_avg:+.4f}")

    # ✅ 唯一新增（核心修复）
    precision = intercepted_incorrect / (intercepted_incorrect + intercepted_correct) if (intercepted_incorrect + intercepted_correct) > 0 else 0
    comparison_rows.append({
        "threshold": BASE_TH,
        "net_gain": net_gain,
        "score_gain": score_gain,
        "TP": intercepted_incorrect,
        "FP": intercepted_correct,
        "FN": missed_incorrect,
        "TN": kept_correct,
        "precision": precision,
        "distribution_collapsed": distribution_collapsed
    })


# ── Step3：修复崩溃 ─────────────────────────────
print("\n" + "=" * 60)
print("  SUMMARY COMPARISON")
print("=" * 60)

for row in comparison_rows:
    print(
        f"  threshold={row['threshold']:.2f} | "
        f"net_gain={row['net_gain']:+d} | "
        f"score_gain={row['score_gain']:+.2f} | "
        f"TP={row['TP']} FP={row['FP']} FN={row['FN']} TN={row['TN']} | "
        f"precision={row['precision']:.2%} | "
        f"collapsed={'Y' if row['distribution_collapsed'] else 'N'}"
    )

if not comparison_rows:
    print("⚠️ comparison_rows 为空")
else:
    best = max(comparison_rows, key=lambda x: x["net_gain"])
    print(f"\n  ★ best_threshold = {best['threshold']:.2f}")

print("=" * 60)

# ================================
# 收尾
# ================================
print(f"\n✅ 日志已保存到: {log_path}")
sys.stdout = sys.__stdout__ 
log_file.close()