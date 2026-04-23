"""Helper: write run_mtrust_test.py with correct content."""
import pathlib

CODE = r'''import json
from datetime import datetime
from mtrust.pipeline.pipeline import MTrustPipeline

pipeline = MTrustPipeline(spec_root="mtrust/specs")

cases = json.load(open("data/cases_core.json", "r", encoding="utf-8"))
rules = open("data/rule.yaml", "r", encoding="utf-8").read()

TASK_NAME = "audit_false_positive"
HIGH_CONF_THRESHOLD = 0.8

AUDIT_DEDUCTION: dict[str, int] = {
    "model_error":  -20,
    "upload_error": -10,
    "zip_error":     -3,
    "none":           0,
}
BASE_SCORE_PER_CASE = 100


def compute_case_score(task: str, is_correct: bool, error_type: str) -> tuple[int, int]:
    """Return (case_score, deduction) for one prediction.

    Only audit_false_positive has a scoring table.
    pipeline.py / confidence.py / evaluators are never touched.
    For other tasks returns (BASE_SCORE_PER_CASE, 0).
    """
    if task != "audit_false_positive":
        return BASE_SCORE_PER_CASE, 0
    if is_correct:
        return BASE_SCORE_PER_CASE, 0
    deduction = AUDIT_DEDUCTION.get(str(error_type).strip(), 0)
    return BASE_SCORE_PER_CASE + deduction, deduction


TP = FP = FN = TN = 0
system_error = 0
high_conf_total = 0
high_conf_correct = 0
total_score = 0
total_deduction = 0
results_detail: list[dict] = []

for i, c in enumerate(cases):
    # label / error_type / score are INTENTIONALLY omitted from model input
    ticket = {
        "content":      c.get("content", ""),
        "rules":        rules,
        "audit_result": c.get("audit_result", ""),
        "error_type":   c.get("error_type", "none"),
    }

    result = pipeline.run(ticket, task=TASK_NAME)

    gt_label    = c.get("label")
    error_type  = c.get("error_type", "none")
    detail      = result.get("detail", {})
    pred_has_fp = detail.get("has_false_positive", False)
    confidence  = result.get("confidence", 0)

    print(f"\n===== Case {i} =====")
    print("RAW RESULT:", result)
    print("label:", gt_label,
          "| pred_has_fp:", pred_has_fp,
          "| conf:", round(confidence, 3),
          "| error_type:", error_type)

    case_record: dict = {
        "case_id":     i,
        "label":       gt_label,
        "error_type":  error_type,
        "pred_has_fp": pred_has_fp,
        "confidence":  confidence,
        "reason":      detail.get("reason", ""),
    }

    if error_type == "system_error":
        system_error += 1
        case_record["status"]     = "skipped_system_error"
        case_record["case_score"] = BASE_SCORE_PER_CASE
        case_record["deduction"]  = 0
        results_detail.append(case_record)
        continue

    gt_has_fp  = (gt_label == "incorrect")
    pred       = pred_has_fp
    is_correct = (gt_has_fp == pred)

    if gt_has_fp and pred:
        TP += 1; case_record["status"] = "TP"
    elif not gt_has_fp and pred:
        FP += 1; case_record["status"] = "FP"
    elif gt_has_fp and not pred:
        FN += 1; case_record["status"] = "FN"
    else:
        TN += 1; case_record["status"] = "TN"

    case_score, deduction = compute_case_score(TASK_NAME, is_correct, error_type)
    total_score     += case_score
    total_deduction += abs(deduction)
    case_record["case_score"] = case_score
    case_record["deduction"]  = deduction

    if confidence >= HIGH_CONF_THRESHOLD:
        high_conf_total += 1
        if is_correct:
            high_conf_correct += 1

    results_detail.append(case_record)


total = TP + FP + FN + TN

print("\n========== 评估结果 ==========")
print(f"TP: {TP} | FP: {FP} | FN: {FN} | TN: {TN}")
print(f"系统异常跳过: {system_error}")

summary: dict = {
    "task": TASK_NAME,
    "TP": TP, "FP": FP, "FN": FN, "TN": TN,
    "system_error": system_error,
}

if total > 0:
    acc       = (TP + TN) / total
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall    = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0
    fp_rate   = FP / (FP + TN) if (FP + TN) > 0 else 0
    fn_rate   = FN / (FN + TP) if (FN + TP) > 0 else 0

    print(f"准确率: {acc:.2f} | 精确率: {precision:.2f} | 召回率: {recall:.2f} | F1: {f1:.2f}")
    print(f"误伤率: {fp_rate:.2f} | 漏检率: {fn_rate:.2f}")

    summary.update({
        "accuracy":  round(acc, 4),
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
        "fp_rate":   round(fp_rate, 4),
        "fn_rate":   round(fn_rate, 4),
    })

if TASK_NAME == "audit_false_positive" and total > 0:
    avg_score    = total_score / total
    max_possible = total * BASE_SCORE_PER_CASE

    print("\n====== 业务评分（工单稽核专用）======")
    print(f"总扣分:   -{total_deduction}")
    print(f"总得分:   {total_score}  (满分 {max_possible})")
    print(f"平均得分: {avg_score:.1f} / {BASE_SCORE_PER_CASE}")

    summary.update({
        "total_score":     total_score,
        "total_deduction": -total_deduction,
        "avg_score":       round(avg_score, 2),
        "max_possible":    max_possible,
    })

if total > 0:
    high_conf_ratio = high_conf_total / total
    high_conf_acc   = (high_conf_correct / high_conf_total) if high_conf_total > 0 else 0

    print("\n====== 高置信度指标 ======")
    print(f"高置信度占比:   {high_conf_ratio:.2f}")
    print(f"高置信度准确率: {high_conf_acc:.2f}")

    summary.update({
        "high_conf_ratio":    round(high_conf_ratio, 4),
        "high_conf_accuracy": round(high_conf_acc, 4),
    })

print("================================")

output = {"summary": summary, "details": results_detail}
filename = f"mtrust_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(filename, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存到: {filename}")
'''

pathlib.Path(r"c:/Users/chaoJ/Desktop/MTrust-main/run_mtrust_test.py").write_text(CODE, encoding="utf-8")
print("DONE — run_mtrust_test.py written successfully")
