import yaml
from mtrust.utils.prompt_builder import build_prompt

with open("mtrust/specs/06_evaluator/audit_false_positive.yaml", encoding="utf-8") as f:
    spec = yaml.safe_load(f)

ctx = {
    "content": "已上传附件 fix_report.pdf，包含完整维修记录",
    "rules": "维修工单必须附带完整维修记录",
    "audit_result": "违规：未提供维修记录"
}

system = (spec.get("instruction") or "").strip()
prompt = build_prompt(spec, ctx, include_instruction=False)

with open("_prompt_out.txt", "w", encoding="utf-8") as f:
    f.write("=== SYSTEM ===\n")
    f.write(system + "\n\n")
    f.write("=== USER ===\n")
    f.write(prompt + "\n")

print("Written to _prompt_out.txt")
print("Examples in spec:", len(spec.get("examples", [])))
print("Post-process threshold:", spec["post_process"][0]["min_confidence"])
