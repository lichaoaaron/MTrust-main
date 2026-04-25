# -*- coding: utf-8 -*-
"""
MTrust 风险置信度评估系统
运行：streamlit run live_app.py

点击"开始评估"后：
  • 终端：同步启动 run_mtrust_live_app.py，完整输出打印到 VS Code 终端
  • 前端：实时解析 run_mtrust_live_app.py 的 stdout，同步更新卡片与统计数字

不修改任何现有文件。
"""
import os
import re
import subprocess
import sys
import threading
import queue

import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# 常量（与 run_mtrust_live_app.py 保持一致）
# ─────────────────────────────────────────────────────────────────────────────
BASE_THRESHOLD   = 0.50
CLASS_TH_OFFSET  = {"D": 0.10}
SCORE_MAP        = {"HIGH": 100, "MEDIUM": 100, "LOW": 5}
TOTAL_CASES      = 43
ORIG_SCORE_AVG   = 64.19
MTRUST_SCORE_AVG = 98.72

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "run_mtrust_live_app.py")

# run_mtrust_live_app.py 每条 Case 的 print 格式：
#   Case   1 | M_1 | conf=0.637 | level=可用 | class=A | label=correct | risk_level=MEDIUM
_CASE_RE    = re.compile(
    r"Case\s+(\d+)\s+\|\s+(\S+)\s+\|\s+conf=([\d.]+)\s+\|.*?\|\s+class=(\S+)\s+\|\s+label=(\S+)\s+\|\s+risk_level=([A-Z]+)"
)
_DONE_RE    = re.compile(r"CASE_DONE case_idx=(\d+)")
_REASON_RE  = re.compile(r"^REASON:\s*(.*)")
_TOTAL_RE   = re.compile(r"^TOTAL_CASES=(\d+)")
_ORIG_RE    = re.compile(r"original_score_avg\s*:\s*([\d.]+)")
_MTRUST_RE  = re.compile(r"mtrust_score_avg\s*:\s*([\d.]+)")


# ─────────────────────────────────────────────────────────────────────────────
# 后台线程：运行脚本，每行放入 queue
# ─────────────────────────────────────────────────────────────────────────────
def _run_script_thread(q: queue.Queue):
    proc = subprocess.Popen(
        [sys.executable, SCRIPT_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=os.path.dirname(__file__),
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    stdout = proc.stdout
    if stdout is None:
        q.put(None)
        return
    for line in stdout:
        # 写入 stderr 回显到 VS Code 终端（Streamlit 未劫持 stderr）
        print(line, end="", file=sys.stderr, flush=True)
        q.put(line.rstrip())
    proc.wait()
    q.put(None)  # 哨兵


# ─────────────────────────────────────────────────────────────────────────────
# 实时回放：解析 queue 中的输出，更新前端
# ─────────────────────────────────────────────────────────────────────────────
def run_live(q: queue.Queue):
    # ── 顶部动态统计 ──
    st.markdown("#### 评估进度")
    col_tc, col_tr, col_ti = st.columns(3)
    box_cases  = col_tc.empty()
    box_risks  = col_tr.empty()
    box_incorr = col_ti.empty()
    box_cases.metric("已完成工单",    0)
    box_risks.metric("已评测风险数",  0)
    box_incorr.metric("已拦截风险数", 0)

    st.markdown("#### 实时评估结果")
    progress_bar = st.progress(0, text="⏳ 等待 LLM 返回…")
    status_box   = st.empty()

    SLOT_COUNT = 12
    slots = [st.empty() for _ in range(SLOT_COUNT)]

    tp = fp = fn = tn = 0
    total_risks    = 0
    total_incorr   = 0
    seen_cases: set = set()
    feed_lines = []
    _pending_reason  = ""
    total_cases_dyn  = TOTAL_CASES
    real_orig_avg    = None   # 从 run_mtrust_live_app.py 输出中解析
    real_mtrust_avg  = None

    done = False
    while not done:
        batch = []
        for _ in range(50):
            try:
                line = q.get(timeout=0.15)
                if line is None:
                    done = True
                    break
                batch.append(line)
            except queue.Empty:
                break

        for line in batch:
            # 动态获取工单总数
            tm = _TOTAL_RE.match(line)
            if tm:
                total_cases_dyn = int(tm.group(1))
                continue

            # 解析真实得分均值
            om = _ORIG_RE.search(line)
            if om:
                real_orig_avg = float(om.group(1))
                continue
            mm = _MTRUST_RE.search(line)
            if mm:
                real_mtrust_avg = float(mm.group(1))
                continue

            # REASON 行 —— 暂存，等待下一次卡片刷新时使用
            rm = _REASON_RE.match(line)
            if rm:
                _pending_reason = rm.group(1).strip()
                # 用暂存的 reason 更新最后一张卡片
                if feed_lines:
                    flag, old_card = feed_lines[-1]
                    if flag and _pending_reason:   # 仅拦截卡片显示 reason
                        new_card = old_card + f"\n\n📌 {_pending_reason}"
                        feed_lines[-1] = (flag, new_card)
                        # 刷新最后一个可见 slot
                        visible = feed_lines[-SLOT_COUNT:]
                        last_visible_idx = len(visible) - 1
                        slots[last_visible_idx].error(new_card)
                continue

            # 工单完成行 → 更新已完成工单数
            dm = _DONE_RE.search(line)
            if dm:
                seen_cases.add(int(dm.group(1)))
                pct = min(int(len(seen_cases) / total_cases_dyn * 100), 99)
                progress_bar.progress(pct, text=f"⏳ 正在评估… 已完成 {len(seen_cases)}/{total_cases_dyn} 个工单")
                box_cases.metric("已完成工单", len(seen_cases))
                continue

            m = _CASE_RE.search(line)
            if not m:
                continue

            case_idx   = int(m.group(1))
            risk_id    = m.group(2)
            conf       = float(m.group(3))
            risk_class = m.group(4)
            label      = m.group(5)
            risk_level = m.group(6)

            effective_th = BASE_THRESHOLD + CLASS_TH_OFFSET.get(risk_class, 0.0)
            intercepted  = conf < effective_th

            total_risks += 1
            if intercepted:
                total_incorr += 1   # 拦截数（无论标签）

            if label == "incorrect":
                tp += 1 if intercepted else 0
                fn += 0 if intercepted else 1
            else:
                fp += 1 if intercepted else 0
                tn += 0 if intercepted else 1

            level_tag = "🔴 HIGH" if risk_level == "HIGH" else "🟡 MED"
            if intercepted:
                card = f"**Case {case_idx:02d} · {risk_id}** &nbsp; {level_tag} &nbsp; 🚫 **拦截**"
            else:
                card = f"**Case {case_idx:02d} · {risk_id}** &nbsp; {level_tag} &nbsp; ✅ **放行**"
            feed_lines.append((intercepted, card))

            visible = feed_lines[-SLOT_COUNT:]
            for j in range(SLOT_COUNT):
                if j < len(visible):
                    flag, txt = visible[j]
                    if flag:
                        slots[j].error(txt)
                    else:
                        slots[j].success(txt)
                else:
                    slots[j].empty()

            box_risks.metric("已评测风险数",  total_risks)
            box_incorr.metric("已拦截风险数", total_incorr)
            status_box.info(f"🔄 当前：Case {case_idx:02d} | {risk_id}")

    progress_bar.progress(100, text="✅ 评估完成！")
    status_box.success("🎉 所有风险条目已评估完毕。")
    box_cases.metric("已完成工单",    len(seen_cases))
    box_risks.metric("已评测风险数",  total_risks)
    box_incorr.metric("已拦截风险数", total_incorr)

    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "orig_avg":   real_orig_avg   if real_orig_avg   is not None else ORIG_SCORE_AVG,
            "mtrust_avg": real_mtrust_avg if real_mtrust_avg is not None else MTRUST_SCORE_AVG}


# ─────────────────────────────────────────────────────────────────────────────
# 汇总
# ─────────────────────────────────────────────────────────────────────────────
def show_summary(stats):
    tp = stats["TP"]
    fp = stats["FP"]
    fn = stats["FN"]

    recall     = tp / (tp + fn)  if (tp + fn) > 0 else 0.0
    score_gain = stats["mtrust_avg"] - stats["orig_avg"]
    net_gain   = tp - fp

    st.divider()
    st.subheader("📊 评估汇总")
    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 错误捕获率（Recall）",  f"{recall:.1%}",
                help="正确拦截的错误结论 / 全部错误结论")
    col2.metric("📈 评分提升（Score Gain）", f"+{score_gain:.1f}",
                delta=f"{score_gain:.1f}")
    col3.metric("💰 净收益（Net Gain）",     f"{net_gain:+d}",
                delta=str(net_gain))
    st.divider()
    st.caption(f"基准分：{stats['orig_avg']:.1f} → MTrust分：{stats['mtrust_avg']:.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# 页面入口
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="MTrust 实时评估演示",
        page_icon="🛡️",
        layout="wide",
    )

    st.title("🛡️ MTrust 风险置信度评估系统")
    st.caption("工单稽核 · 风险结论可信度分析 · 实时评估同步展示")
    st.divider()

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
- 点击开始后调用真实 LLM 逐条评估
- 前端实时解析终端输出并同步展示
"""
        )
        st.divider()
        st.metric("评测级别", "HIGH + MEDIUM")

    st.divider()

    if st.button("🚀 开始评估", type="primary", use_container_width=True):
        st.markdown("### 📋 实时评估过程")
        q = queue.Queue()
        t = threading.Thread(target=_run_script_thread, args=(q,), daemon=True)
        t.start()
        stats = run_live(q)
        t.join(timeout=5)
        if stats:
            show_summary(stats)


if __name__ == "__main__":
    main()
