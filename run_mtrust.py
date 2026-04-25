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

_real_stdout = sys.stdout   # 保存真实 stdout，避免被 Streamlit 的 DeltaGenerator 替换
sys.stdout = Tee(sys.stdout, log_file)

# ================================
# 原有代码（完全不动）
# ================================

THRESHOLDS = [0.5]  #[round(x * 0.01, 2) for x in range(20, 56)]  # 0.20 ~ 0.55 at 0.01 steps

pipeline = MTrustPipeline(spec_root="mtrust/specs")

cases = json.load(open("data/cases_risk_level_simple.json", "r", encoding="utf-8"))
rules = open("data/rule.yaml", "r", encoding="utf-8").read()

TASK_NAME = "risk_confidence"
EVAL_LEVELS = {"HIGH", "MEDIUM"}

SCORE_MAP = {
    "HIGH": 100,
    "MEDIUM": 100,
    "LOW": 5,
}

os.makedirs("output", exist_ok=True)

# 磁盘缓存路径，避免重复调用 LLM
LLM_CACHE_PATH = "output/llm_cache.json"


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


def _infer_risk_class(reason: str) -> str:
    """从 reason 字段首个类型标记推断 A/B/C/D/E 类。"""
    if not reason:
        return "?"
    for cls in ("A", "B", "C", "D", "E"):
        if reason.strip().startswith(cls + "类"):
            return cls
    import re
    m = re.search(r'\b([ABCDE])类', reason)
    return m.group(1) if m else "?"


# ── Step1：LLM调用（始终重新评估，不读缓存）─────────────────────
print("\n" + "=" * 60)
print("  正在调用 LLM...")
print("=" * 60)
# 输出工单总数，供前端动态获取（不依赖硬编码）
print(f"TOTAL_CASES={len(cases)}")

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
        reason = detail.get("reason", "")
        risk_class = _infer_risk_class(reason)

        print(f"  Case {case_idx:3d} | {risk['risk_id']} | conf={confidence:.3f} | level={result.get('confidence_level','')} | class={risk_class} | label={risk.get('label','correct')} | risk_level={risk.get('risk_level','')}")
        # 单独一行输出 reason，供前端解析展示（以 REASON: 为前缀，内容不含换行）
        reason_oneline = reason.strip().replace("\n", " ")
        print(f"REASON: {reason_oneline}")

        case_risks.append({
            "risk_id": risk["risk_id"],
            "risk_level": risk["risk_level"],
            "label": risk.get("label", "correct"),
            "confidence": round(confidence, 4),
            "reason": reason,
        })

    llm_cache.append({
        "case_idx": case_idx,
        "error_type": error_type,
        "risks": case_risks,
        "all_risks": risks,
    })
    # 每个工单处理完毕后输出一行，让前端统计完成工单数（含无风险工单）
    print(f"CASE_DONE case_idx={case_idx}")

with open(LLM_CACHE_PATH, "w", encoding="utf-8") as f:
    json.dump(llm_cache, f, ensure_ascii=False, indent=2)

# 同时单独保存一份与本次 log 同名的 JSON
run_json_path = log_path.replace(".log", ".json")
with open(run_json_path, "w", encoding="utf-8") as f:
    json.dump(llm_cache, f, ensure_ascii=False, indent=2)

print(f"\n  LLM 调用完毕，共处理 {len(cases)} 个工单。已缓存到 {LLM_CACHE_PATH}")
print(f"  本次运行 JSON 已单独保存到: {run_json_path}")


# ── Step2：多阈值评估（细粒度 + 类感知阈值）──────────
MARGIN = 0.05

# 类感知阈值偏移：D类（主观语义推断）本身误判率高，用更高阈值拦截
# 其他类别（A/B/C/E）保持 BASE_TH
CLASS_TH_OFFSET = {
    "D": 0.10,   # D类额外+0.10（更激进拦截）
}

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
            reason     = rd.get("reason", "")

            # 类感知阈值
            risk_class = _infer_risk_class(reason)
            effective_th = BASE_TH + CLASS_TH_OFFSET.get(risk_class, 0.0)

            if distribution_collapsed:
                intercepted = confidence < BASE_TH
            else:
                intercepted = confidence < effective_th


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
        # calc_score uses a single threshold, so we approximate with BASE_TH;
        # the per-risk intercept decisions are already in pred_conf comparison above.
        # To correctly reflect class-aware decisions, re-score using intercepted flag:
        mtrust_score = 100
        for rd in case_risks:
            rid   = rd["risk_id"]
            label = rd["label"]
            reason = rd.get("reason", "")
            risk_class = _infer_risk_class(reason)
            effective_th = BASE_TH + CLASS_TH_OFFSET.get(risk_class, 0.0)
            conf = rd["confidence"]
            level = rd["risk_level"]
            if distribution_collapsed:
                was_intercepted = conf < BASE_TH
            else:
                was_intercepted = conf < effective_th
            if label == "incorrect" and not was_intercepted:
                mtrust_score -= SCORE_MAP.get(level, 0)
        # also subtract for all_risks not in case_risks (not in EVAL_LEVELS, use orig deduct)
        evaluated_ids = {rd["risk_id"] for rd in case_risks}
        for r in all_risks:
            if r["risk_id"] not in evaluated_ids:
                if r.get("label", "correct") == "incorrect":
                    mtrust_score -= SCORE_MAP.get(r.get("risk_level", "LOW"), 0)
        mtrust_score = max(mtrust_score, 0)

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
    print(f"  THRESHOLD = {TH:.2f}  汇总（类感知阈值：D类+{CLASS_TH_OFFSET.get('D',0):.2f}）")
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
sys.stdout = _real_stdout   # 还原到真实 stdout（而非 Streamlit DeltaGenerator）
log_file.close()