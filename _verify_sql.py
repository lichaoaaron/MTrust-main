from mtrust.evaluators.spec_evaluator import SpecEvaluator
from mtrust.utils.prompt_builder import build_prompt

e = SpecEvaluator("sql_validation")
ctx = {
    "query": "SELECT id, name FROM users WHERE id=1",
    "schema": "users(id INT, name VARCHAR, email VARCHAR)"
}
prompt = build_prompt(e.spec, ctx, include_instruction=False)
system = (e.spec.get("instruction") or "").strip()

print("=== SPEC LOADED ===")
print("task       :", e.spec.get("task"))
print("fields     :", e.spec.get("input_fields"))
print("schema keys:", list(e._output_fields.keys()))
print()
print("=== SYSTEM PROMPT (first 80 chars) ===")
print(system[:80])
print()
print("=== USER PROMPT ===")
print(prompt)
