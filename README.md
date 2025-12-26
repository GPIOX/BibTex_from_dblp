# DBLP BibTeX 批量获取工具

基于 FastAPI 的轻量网页与接口，批量从 DBLP 获取论文 BibTeX。对应代码：`app.py`。

## 环境要求
- Python ≥ 3.9（推荐 3.10+）
- 依赖：`fastapi`、`uvicorn`、`requests`、`pydantic`

安装依赖：

```bash
pip install fastapi uvicorn requests pydantic
```

## 启动方式
- 方式一：直接运行 Python（默认端口 `8000`）

```bash
python app.py
# 访问：http://localhost:8000/
```

- 方式二：使用 Uvicorn 指定端口（例如 `8003`）

```bash
uvicorn app:app --host 0.0.0.0 --port 8003
# 访问：http://localhost:8003/
```

对应代码位置：
- 页面路由 `GET /`：`app.py:158`
- 搜索接口 `POST /api/search`：`app.py:115`
- 健康检查 `GET /api/check-dblp`：`app.py:133`
- 批量下载 `POST /api/download`：`app.py:142`
- 代理环境变量支持：`HTTP_PROXY`、`HTTPS_PROXY`（`app.py:12-20`）

## 使用说明（网页）
- 打开根页 `/`，输入关键词或论文标题（每行一个），点击“开始搜索”。
- 结果区展示标题、作者、年份与 BibTeX；可点击“下载所有 BibTeX”。
- 无需 API Key；若网络不稳定，稍后重试。

## 接口说明（API）
- `POST /api/search`
  - 请求体：
    ```json
    {"keywords": ["paper title 1", "paper title 2"], "max_results": 5}
    ```
  - 响应：
    ```json
    {"total": 2, "results": [{"title": "...", "authors": "A, B", "year": "2021", "bibtex": "@..."}]}
    ```
  - 备注：无结果时返回 `200`，`{"total": 0, "results": []}`。

- `GET /api/check-dblp`
  - 用于检测 DBLP 可达性，返回：`{"reachable": true/false}`。

- `POST /api/download`
  - 请求体为 `results` 列表（即 `POST /api/search` 的 `results` 字段），返回 `references.bib` 文件。

## 示例
使用 `curl` 调用搜索接口：

```bash
curl -X POST http://localhost:8003/api/search \
  -H 'Content-Type: application/json' \
  -d '{"keywords":["Attention is all you need"],"max_results":3}'
```

Python 调用示例：

```python
import requests
url = 'http://localhost:8003/api/search'
payload = {"keywords": ["Modular interactive video object segmentation"], "max_results": 3}
r = requests.post(url, json=payload)
print(r.status_code)
print(r.json())
```

## Fastapi可视化界面
初始界面
![image](https://github.com/GPIOX/BibTex_from_dblp/blob/master/image/fig1.png)

批量搜索结果
![image](https://github.com/GPIOX/BibTex_from_dblp/blob/master/image/fig2.png)


## 代理支持（可选）
如需经代理访问 DBLP，设置环境变量：

```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
```

## 常见问题
- 返回 `{"total": 0, "results": []}`：说明关键词未命中，可尝试更完整的论文标题或更换关键词。
- 前端点击无响应或脚本错误：强制刷新浏览器（Ctrl+F5）；确保服务器端口与访问地址一致。

### TODO
- [ ] 增加搜索缓存机制，避免重复请求
- [ ] 增加健康检查接口，监控服务运行状态
- [ ] 添加其他数据库的支持，做对比验证