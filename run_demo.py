from mtrust.pipeline.pipeline import MTrustPipeline

pipeline = MTrustPipeline("mtrust/specs")

# ticket = {
#     "content": "用户反馈登录失败，系统报错 timeout",
#     "model_output": {
#         "risk_level": "none"
#     }
# }


cases = [
    # 1️⃣ 应该纠错
    {
        "name": "高风险低置信度",
        "content": "系统异常 error timeout，用户无法使用",
        "model_output": {"risk_level": "high"}
    },
    # 2️⃣ 不纠错
    {
        "name": "高置信度",
        "content": "正常请求返回成功",
        "model_output": {"risk_level": "low"}
    },
    # 3️⃣ 不触发
    {
        "name": "低风险无信号",
        "content": "页面样式有点问题",
        "model_output": {"risk_level": "low"}
    }
]

# ticket = {
#     "content": "系统异常 error timeout，用户无法使用",
#     "model_output": {
#         "risk_level": "high"   # ⭐ 关键
#     }
# }


for case in cases:
    result = pipeline.run(case)
    print(case["name"], result)

# result = pipeline.run(ticket)

# print(result)