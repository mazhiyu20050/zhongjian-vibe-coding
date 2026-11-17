# 众见｜Vibe Coding 参赛评审版

众见是一个多人物视角的问答工具：先并排看看不同人物如何分析同一个问题，核对出处，再选一个视角继续聊。这个公开仓库只用于比赛评审，不是含完整语料与人物资产的日常版。

## 10 分钟快速复现（推荐 Windows PowerShell）

准备 Git、Python 3.11 / 3.12 和浏览器。下载代码和安装依赖需要网络；启动后的固定案例无需联网或 API 密钥。

```powershell
git clone https://github.com/mazhiyu20050/zhongjian-vibe-coding.git
cd zhongjian-vibe-coding
py -3.12 -m venv .review-venv
.\.review-venv\Scripts\python.exe -m pip install -r requirements.txt
.\.review-venv\Scripts\python.exe reviewer_demo.py
```

已有 Python 3.11 时，将 `py -3.12` 换成 `py -3.11`。如果 Python 是经 uv 安装、没有注册到 Windows 启动器，用下面两行替换创建环境和安装依赖，再执行同一个启动命令：

```powershell
uv venv --python 3.12 .review-venv
uv pip install --python .\.review-venv\Scripts\python.exe -r requirements.txt
```

终端打印本机 URL 后，在浏览器打开。端口已占用时给启动命令加 `--port 0`；按 Ctrl+C 退出。不需要先安装桌面 EXE。

### 评审建议操作

1. 发送首页预填的问题，比较三张人物观点卡。
2. 点击「详读原文」，查看这张卡的短引和出处；鼠标移到最右侧打开对话脉络。
3. 点击孔子卡片正文进入单人对话，追问「如果今晚还没交，我该怎么做？」。
4. 返回或展开原对话；打开左侧栏，检查原讨论和单聊是两条记录。

**固定案例说明：** 此入口用公开评审样例和临时数据验证交互及出处呈现，不调用付费模型、不接入完整第三方语料、不读取参赛者的私人历史。实时任意提问和人物下载功能不属于公开精简版的复现承诺。

## 验收命令

```powershell
.\.review-venv\Scripts\python.exe -m unittest test_reviewer_demo test_history_actions test_project_menu test_conversation_outline -v
node --test test_chat_timeline.cjs test_agent_wheel.cjs test_agent_search.cjs
```

Node.js 只用于可选的前端回归。历史提交和其余测试文件可用于了解演进；依赖完整语料、安装器或桌面资产的旧测试不属于本公开快验。依赖清单见 `requirements.txt`；`.env.example` 是原正式模式的环境变量模板，不会自动加载，评审入口不需要填密钥。

## 代码结构与演进记录

- `web/`：界面、人物轮盘、会话和对话脉络。
- `web_server.py`、`agent.py`：本地路由、上下文与模型编排。
- `person_skills.py`、`query.py`、`conversation_outline.py`：人物选择、本地检索和脉络校验。
- `reviewer_demo.py`：免密钥的固定评审案例。
- [提交映射与公开范围](docs/PUBLIC_HISTORY.md)：每条公开历史映射回真实原提交。源历史首次记录已是原型，并非从空白开始。

公开历史按原顺序筛选了原创代码和必要说明，因此 Git 哈希与私有仓库不同；没有把多个开发步骤压成一次提交。未公开授权未核实的全文、肖像、下载包、内部日志与私人材料。样例语料、旧版与本版的范围请以本页为准。
