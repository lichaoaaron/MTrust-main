# -*- coding: utf-8 -*-
"""
MTrust 风险置信度评估系统
Demo 展示层 —— 仅读取 llm_cache.json，伪实时回放，不调用任何 LLM / pipeline
运行：streamlit run demo_app.py
"""
import json
import time
import math
import os
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────
CACHE_PATH = os.path.join(os.path.dirname(__file__), "output", "run_20260424_161119.json")
BASE_THRESHOLD = 0.50        # 最优基础阈值
CLASS_TH_OFFSET = {"D": 0.10}  # D类（主观语义推断）额外偏移
SCORE_MAP = {"HIGH": 100, "MEDIUM": 100, "LOW": 5}
EVAL_LEVELS = {"HIGH", "MEDIUM"}
TOTAL_CASES = 43             # 数据集总工单数
TOTAL_DEMO_SECONDS = 25      # 总回放时长控制在 25s 左右
# 由 run_mtrust_test.py 离线计算的准确得分（threshold=0.50，D类+0.10）
ORIG_SCORE_AVG   = 64.19
MTRUST_SCORE_AVG = 96.40


# ─────────────────────────────────────────────────────────────────────────────
# ① 数据加载
# ─────────────────────────────────────────────────────────────────────────────
def _infer_class(reason: str) -> str:
    import re
    if not reason:
        return "?"
    if reason.strip().startswith(("A类", "B类", "C类", "D类", "E类")):
        return reason.strip()[0]
    m = re.search(r'\b([ABCDE])类', reason)
    return m.group(1) if m else "?"


def load_data():
    """加载离线计算好的 llm_cache.json，返回回放用的事件列表。"""
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    events = []
    for cached in raw:
        case_idx = cached["case_idx"]
        case_events = []
        for rd in cached.get("risks", []):
            if rd.get("risk_level") not in EVAL_LEVELS:
                continue
            conf = rd["confidence"]
            reason_full = rd.get("reason", "")
            risk_class = _infer_class(reason_full)
            effective_th = BASE_THRESHOLD + CLASS_TH_OFFSET.get(risk_class, 0.0)
            intercepted = conf < effective_th
            reason_full = reason_full.strip()
            case_events.append({
                "case_idx": case_idx,
                "risk_id": rd["risk_id"],
                "risk_level": rd["risk_level"],
                "label": rd.get("label", "correct"),
                "confidence": conf,
                "intercepted": intercepted,
                "reason_full": reason_full,
                "sentinel": False,
            })
        if case_events:
            events.extend(case_events)
        else:
            # 该工单无 HIGH/MEDIUM 风险，插入哨兵以保证工单计数正确
            events.append({
                "case_idx": case_idx,
                "sentinel": True,
            })
    return events


# ─────────────────────────────────────────────────────────────────────────────
# ② 伪实时回放
# ─────────────────────────────────────────────────────────────────────────────
def playback_results(events, metric_cases, metric_risks, metric_incorr, total_cases, total_risks, total_incorr):
    """逐条回放事件，显示进度条 + 动态结果卡片，返回统计 dict。"""
    n = len(events)
    if n == 0:
        st.warning("缓存中无可评测的事件。")
        return {}

    delay_per_event = TOTAL_DEMO_SECONDS / n

    # 统计量
    tp = fp = fn = tn = 0
    seen_cases = set()
    seen_incorr = 0

    progress_bar = st.progress(0, text="⏳ 正在评估中，请稍候…")
    status_box   = st.empty()

    # 预分配 12 个固定 slot，彻底避免重复渲染
    SLOT_COUNT = 12
    slots = [st.empty() for _ in range(SLOT_COUNT)]
    # 滚动缓冲区
    feed_lines = []

    for i, ev in enumerate(events):
        # 哨兵事件：只更新工单计数，不渲染卡片
        if ev.get("sentinel"):
            seen_cases.add(ev["case_idx"])
            metric_cases.metric("工单总数", len(seen_cases))
            time.sleep(delay_per_event)
            continue

        conf        = ev["confidence"]
        intercepted = ev["intercepted"]
        label       = ev["label"]
        case_idx    = ev["case_idx"]
        risk_id     = ev["risk_id"]
        reason      = ev["reason_full"]

        # 统计
        if label == "incorrect":
            if intercepted:
                tp += 1
            else:
                fn += 1
        else:
            if intercepted:
                fp += 1
            else:
                tn += 1

        # 动态更新顶部指标
        seen_cases.add(case_idx)
        if intercepted:
            seen_incorr += 1
        risk_count = sum(1 for e in events[:i+1] if not e.get("sentinel"))
        metric_cases.metric("工单总数",     len(seen_cases))
        metric_risks.metric("参评风险数",   risk_count)
        metric_incorr.metric("错误稽核风险", seen_incorr)

        # 构造展示行（无置信度；拦截时显示完整 reason）
        level_tag = "🔴 HIGH" if ev["risk_level"] == "HIGH" else "🟡 MED"
        if intercepted:
            line = (
                f"**Case {case_idx:02d} · {risk_id}** &nbsp; {level_tag} &nbsp; 🚫 **拦截**"
                + (f"\n\n📌 {reason}" if reason else "")
            )
        else:
            line = (
                f"**Case {case_idx:02d} · {risk_id}** &nbsp; {level_tag} &nbsp; ✅ **放行**"
            )

        feed_lines.append((intercepted, line))

        # 刷新固定 slots —— 每个 slot 写一次，无重复
        visible = feed_lines[-SLOT_COUNT:]
        for j in range(SLOT_COUNT):
            if j < len(visible):
                intercept_flag, txt = visible[j]
                if intercept_flag:
                    slots[j].error(txt)
                else:
                    slots[j].success(txt)
            else:
                slots[j].empty()

        # 进度条 & 状态
        pct = int((i + 1) / n * 100)
        progress_bar.progress(pct, text=f"⏳ 正在评估中… {i+1}/{n} 条风险")
        status_box.info(f"🔄 当前：Case {case_idx:02d} | {risk_id}")

        time.sleep(delay_per_event)

    progress_bar.progress(100, text="✅ 评估完成！")
    status_box.success("🎉 所有风险条目已评估完毕。")

    # 用离线准确值，避免仅统计 EVAL_LEVELS 风险导致的偏差
    orig_avg   = ORIG_SCORE_AVG
    mtrust_avg = MTRUST_SCORE_AVG

    return {
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "orig_avg": orig_avg,
        "mtrust_avg": mtrust_avg,
    }


def _count_cases(events):
    return len({ev["case_idx"] for ev in events})


def _calc_avg_score(events, use_mtrust: bool):
    """按 case 汇总得分，返回平均（分母固定为 TOTAL_CASES=43）。"""
    from collections import defaultdict
    case_scores = defaultdict(lambda: 100)
    for ev in events:
        if ev["label"] == "incorrect":
            if use_mtrust:
                if not ev["intercepted"]:
                    case_scores[ev["case_idx"]] -= SCORE_MAP.get(ev["risk_level"], 0)
            else:
                case_scores[ev["case_idx"]] -= SCORE_MAP.get(ev["risk_level"], 0)
    # 全部 43 个工单，无 risks 的 case 得分为 100
    scores = [max(0, case_scores[c]) for c in range(TOTAL_CASES)]
    return sum(scores) / TOTAL_CASES


# ─────────────────────────────────────────────────────────────────────────────
# ③ 汇总展示
# ─────────────────────────────────────────────────────────────────────────────
def show_summary(stats):
    tp = stats["TP"]
    fp = stats["FP"]
    fn = stats["FN"]
    tn = stats["TN"]

    recall    = tp / (tp + fn)  if (tp + fn) > 0 else 0.0
    score_gain = stats["mtrust_avg"] - stats["orig_avg"]
    net_gain   = tp - fp

    st.divider()
    st.subheader("📊 评估汇总")

    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 错误捕获率（Recall）",  f"{recall:.1%}",      help="正确拦截的错误结论 / 全部错误结论")
    col2.metric("📈 评分提升（Score Gain）", f"+{score_gain:.1f}", delta=f"{score_gain:.1f}")
    col3.metric("💰 净收益（Net Gain）",     f"{net_gain:+d}",     delta=str(net_gain))

    st.divider()
    st.caption(
        f"基准分：{stats['orig_avg']:.1f} → MTrust分：{stats['mtrust_avg']:.1f}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 页面入口
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="MTrust 风险置信度评估演示系统",
        page_icon="🛡️",
        layout="wide",
    )

    st.title("🛡️ MTrust 风险置信度评估演示系统")
    st.caption("工单稽核 · 风险结论可信度分析 · 自动拦截低置信度风险")

    st.divider()

    # ── 侧栏说明 ──
    with st.sidebar:
        st.header("ℹ️ 系统说明")
        st.markdown(
            """
**MTrust** 是面向工单稽核场景的风险置信度评估框架。

- 自动判断每条风险结论的**可信度**
- 低置信度结论自动**拦截**，不进入业务流
- 高置信度结论**放行**，直接用于决策

---
**评估流程**
1. 加载工单风险数据
2. 逐条计算置信度分数
3. 按阈值决策：拦截 / 放行
4. 输出综合评分提升报告
"""
        )
        st.divider()
        st.metric("评测级别", "HIGH + MEDIUM")

    # ── 加载数据 ──
    try:
        events = load_data()
    except FileNotFoundError:
        st.error(f"❌ 未找到缓存文件：`{CACHE_PATH}`\n\n请先运行 `python run_mtrust_test.py` 生成缓存。")
        return

    total_cases  = len({ev["case_idx"] for ev in events})
    total_risks  = sum(1 for ev in events if not ev.get("sentinel"))
    total_incorr = sum(1 for ev in events if not ev.get("sentinel") and ev["intercepted"])

    col_a, col_b, col_c = st.columns(3)
    metric_cases  = col_a.empty()
    metric_risks  = col_b.empty()
    metric_incorr = col_c.empty()
    metric_cases.metric("工单总数",     0)
    metric_risks.metric("参评风险数",   0)
    metric_incorr.metric("错误稽核风险", 0)

    st.divider()

    # ── 开始按钮 ──
    if st.button("🚀 开始评估", type="primary", use_container_width=True):
        st.markdown("### 📋 实时评估过程")
        stats = playback_results(events, metric_cases, metric_risks, metric_incorr, total_cases, total_risks, total_incorr)
        if stats:
            time.sleep(1.5)
            show_summary(stats)


if __name__ == "__main__":
    main()
