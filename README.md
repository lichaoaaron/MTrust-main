# MTrust 服务部署说明

## 1. 环境要求
- Python >= 3.9
- 已安装 uv（推荐）

## 2. 安装依赖
uv sync

## 3. 启动服务
uv run python -m uvicorn service.app:app --host 0.0.0.0 --port 8000

## 4. 验证服务

健康检查：
http://ip:8000/health

接口文档：
http://ip:8000/docs

测试调用：

curl -X POST http://ip:8000/mtrust/evaluate \
-H "Content-Type: application/json" \
-d '{"ticket":"数据库连接超时"}'

## 5. 返回示例

{
  "code": 0,
  "message": "success",
  "data": {
    "confidence": 0.7,
    "risk": "medium",
    "has_false_positive": true,
    "detail": {}
  },
  "cost_time": 0
}