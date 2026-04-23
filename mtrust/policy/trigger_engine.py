class TriggerEngine:

    def __init__(self, policy):
        self.rules = policy.get("rules", [])

    def evaluate_condition(self, condition, context):
        try:
            return eval(condition, {}, context)
        except Exception:
            return False

    def should_trigger(self, context):
        ticket = context.get("ticket", "")
        if isinstance(ticket, dict):
            ticket = ticket.get("content", "")
            
        if "超时" in ticket:
            return "medium"
        elif "失败" in ticket:
            return "high"
        else:
            return "low"