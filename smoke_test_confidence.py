from mtrust.pipeline.pipeline import MTrustPipeline
import json

pipeline = MTrustPipeline(spec_root="mtrust/specs")
cases = json.load(open("data/cases_risk_level.json", encoding="utf-8"))
rules = open("data/rule.yaml", encoding="utf-8").read()

print("Testing 3 risks from first 2 cases:")
tested = 0
for c in cases[:3]:
    for risk in c.get("risks", [])[:2]:
        ticket = {
            "content": c.get("content", ""),
            "risk_message": risk.get("risk_message", ""),
            "rules": rules,
        }
        r = pipeline.run(ticket, task="risk_confidence")
        print(f"  conf={r.get('confidence'):.3f}  level={r.get('confidence_level')}  label={risk.get('label','?')}")
        tested += 1
        if tested >= 5:
            break
    if tested >= 5:
        break

print("Done.")
