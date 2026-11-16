# 众见 · Zhongjian

人物 Skill 路由 + 本地 RAG 的观点查询 Agent。输入困惑，从二十位人物的本地原著或已核验公开短引中检索，生成不同视角的解答并校验引用。

## 评审快速复现（无需密钥）

准备 Python 3.11 或 3.12 和浏览器。安装依赖需要网络；启动后的演示只使用本地数据。

Windows PowerShell：

```powershell
py -3 -m venv .review-venv
.\.review-venv\Scripts\python.exe -m pip install -r requirements.txt
.\.review-venv\Scripts\python.exe reviewer_demo.py
```

macOS / Linux（命令供复现，当前交付未做实机验证）：

```sh
python3 -m venv .review-venv
.review-venv/bin/python -m pip install -r requirements.txt
.review-venv/bin/python reviewer_demo.py
```

1. 打开终端打印的本机网址，发送预填的问题「小组作业里队友拖延，我要不要直接接手？」。
2. 对比三张卡片；点「详读原文」核对出处，或点右侧边缘的 `‹` 查看本例的固定共同点。
3. 点击孔子卡片正文进入单人物对话，输入「如果今晚还没交，我该怎么做？」；可继续读取上方原对话，或点左上角「返回」。
4. 打开左侧栏，检查多人对话和人物对话是两条记录。按 Ctrl+C 停止，临时数据随之清理。端口冲突时加 `--port 0`。

页面明示「离线评审演示」：多人观点、人物详解和共同点均为固定样例，引用来自本地语料。演示不读取本机正式会话、密钥，也不调用在线模型。任意问题的真实模型体验见下方「启动网页版」。`.env.example` 仅列配置项，不会被自动加载。

快速验收：用同一虚拟环境的 Python 执行 `python -m unittest test_reviewer_demo test_history_actions test_project_menu -v` 和 `python verify_corpus.py`。安装 Node.js 后可另跑 `node --test test_chat_timeline.cjs test_agent_wheel.cjs`。评审入口与源码对应 Git 提交，免密钥演示通过不代表在线服务已验证。

## Windows 轻量桌面版

推荐下载 `Zhongjian-Setup-0.3.0-x64.exe`，这是唯一需要下载的文件：按中文向导安装，支持桌面快捷方式与 Windows 卸载入口，卸载保留个人数据。说明见 [安装与下载](docs/INSTALLER.md)。`build_installer.ps1` 可从已有桌面构建生成安装包和本地下载页。

完整解压桌面发布包后，双击 `众见.exe`。首次在设置中填写官方 DeepSeek 密钥与模型名称；无需安装 Python，也无需手动启动服务。界面保留四宫格与展开阅读。

- pywebview + Windows Edge WebView2 原生窗口，Python 与资料库随包分发。
- 独立动态本机端口，关闭窗口停止自己的后台；不占用原网页版的 8765 端口。
- 配置和收藏存于 `%LOCALAPPDATA%\Zhongjian`，密钥使用 Windows DPAPI 加密。
- 当前为未签名便携版；仍需联网调用 DeepSeek。首次启动需已安装 WebView2 Runtime。
- 从源码打包：`powershell -ExecutionPolicy Bypass -File .\build_desktop.ps1`。输出位于 `dist`；说明见 [桌面使用说明](docs/DESKTOP_QUICKSTART.txt)。

## 启动网页版（Python 3.11+）

在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$secret = Read-Host 'DeepSeek API Key' -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
$env:DEEPSEEK_MODEL = 'deepseek-flash'
python web_server.py --port 8765
```

打开 http://127.0.0.1:8765/ 。若账户不支持此模型，用账户可用且支持工具调用的模型名替换。API 调用可能产生费用。测试采用模拟客户端，不需要密钥。

Windows 也可运行 `powershell -ExecutionPolicy Bypass -File .\配置密钥.ps1` 隐藏输入并使用当前 Windows 用户加密保存密钥，再运行 `powershell -ExecutionPolicy Bypass -File .\启动网页.ps1`。启动脚本兼容原开发环境，普通电脑会使用 PATH 中的 Python；推荐激活虚拟环境后直接运行上面的 Python 命令。

Linux/macOS：使用 `source .venv/bin/activate` 和 `export DEEPSEEK_API_KEY=...`，再执行同一 Python 启动命令。启动后仅监听本机；未配置密钥时可打开页面，在线回答需要密钥。关闭服务按 Ctrl+C。

## 实现流程

问题检验（必要时最多两次简短追问）→ 根据人物 Skill 选人 → 工具调用检索本地语料 → 结合原文与 Skill 生成 → 校验原文片段、来源与结构 → 极简卡片及展开讲解。

- RAG：繁简归一化的关键词检索 + 人物核心思想原文锚点；目前没有向量数据库，也未微调模型。
- 前端：原生 HTML/CSS/JavaScript；后端：Python ThreadingHTTPServer；收藏：SQLite。
- 每次默认选择四位最相关人物，各一张卡片；点名时限定人物；支持原文、AI 译意、展开阅读、收藏及建议侧重。
- 占比是模型估计的行动侧重，不是客观评分、真实概率或历史人物本人意见。缺少依据时显示待定。
- 人物讲解是依据原著与 Skill 的 AI 角色化解读，不是历史人物真实发言；弗洛伊德的历史理论不作临床诊断。

## 数据与复现

已附清洗语料及对应原始快照，不需要开发者电脑上的目录。资料来源、哈希、处理方法与再生成命令见 [数据处理说明](docs/DATA_PROCESSING.md)。第三方文本及 Skill 的来源权利单列，不因存入本仓库而改变；仓库默认私有，公开前须复核相应版本和转载范围。

## 测试

```powershell
python -m unittest discover -s . -v
python query.py --offline-demo
```

自动测试不调用付费 API，覆盖检索、引用、Skill 路由、工具执行、收藏确认、格式修复、占比及网页接口。真实 API 与浏览器检查属于另外的联调证据，不等于所有回答都正确。

- [本次交付测试日志](reports/unit-tests.txt)
- [测试与验收说明](docs/TESTING.md)
- [AI 工具使用记录](docs/AI_USAGE.md)

## 目录

| 路径 | 用途 |
|---|---|
| `agent.py` | 多轮对话、模型工具路由与有界修复 |
| `query.py` / `thinkers.py` | 检索、思想锚点与引用校验 |
| `skills/people/` | 项目专用人物 Skill 和哈希清单 |
| `data/raw/` / `data/processed/` | 来源快照、清洗语料与处理清单 |
| `web_server.py` / `web/` | 本地网页与 API |
| `source_details.py` | 展开阅读与人物专属解读 |
| `test_*.py` | 自动化回归测试 |

## 隐私与边界

本次提交排除 API 密钥、Windows 加密密钥文件、收藏数据库、运行时日志以及私人聊天截图。运行时问题和候选资料会发送到配置的 DeepSeek 服务；模型会话状态在进程内存；网页与桌面历史问题、回答及用户确认的收藏保存在本机 SQLite，无云端同步。原文匹配校验不能证明解读一定正确；语料未完成逐段校勘。当前不支持向量语义召回，历史对话话题切分仍可能影响相关性，模型的排序、语气和建议需持续评估。

## 2026-10-19：扩展为十二位人物

王阳明、毛泽东、弗洛伊德；新增孔子、老子、庄子、苏轼、鲁迅、尼采、叔本华，以及孙宇晨、马斯克。每位均有独立 Skill、原文来源和真实思想锚点，不是仅增加名称。系统从完整目录选人，仍保持极简页面，默认以两行两列四宫格呈现，不会同时铺出十二张卡片。

**覆盖范围不同**：古典与近现代七位新增人物使用有上下文的章节/段落；孙宇晨和马斯克各先接入三个独立来源的短引，只覆盖有限的学习、项目与公开目标，不代表完整人格或全部思想。现代人物不自动成为心理或投资权威。英文原句保持原样，页面显示的是单独生成的中文译意。

- [人物与覆盖范围](docs/PEOPLE.md)
- [本次完整回归日志](reports/unit-tests.txt)
- [语料与思想锚点审计](reports/expanded-corpus-audit.json)
- [五位人物真实接口联调](reports/expanded-api-smoke.json)

`python verify_corpus.py` 检查来源 SHA256、Skill 哈希及所有概念的原句锚点。`python evaluate_expansion.py --live` 是显式付费接口测试，使用合成开发问题，需自行配置密钥。

## 四宫格界面
桌面端默认四位人物，两行两列独立卡片；保持点开详情、简短标题、解读与建议占比。窄屏自动单列，防止文字挤压；明确点名少于四人时尊重点名，不添加无关人物。扩展工具选人、检索锚点和引用校验均支持四位，不是仅在前端拼四个框。

## 多行输入与格式恢复
输入框自动换行并随文字增高；Enter发送、Shift+Enter换行，中文输入法确认文字时不误发送。查询失败保留草稿，已有成功结果也保留，不用技术JSON报错替换整页。每轮最多8次模型请求，其中工具阶段最多5轮、最多8次工具执行；最终结果的格式修复最多2次，缺失/截断接口回复最多再生成1次，仍受8次请求总上限约束。修复后仍走原文和结构校验，不编造补全引用。

## 交互终端版（一条命令）

Windows 在仓库根目录运行 ` .\众见.cmd `，或双击此文件。进入后直接输入自然语言问题，不需要编写PowerShell变量或手动请求接口。

- 输入 `1`～`4`：展开对应人物的专属详解；输入 `更多1` 看相关篇章。
- 输入 `返回`：返回上层；`摘要`：回到人物概览；`原文`：显示选中片段。
- 直接继续输入自然语言：沿用当前终端会话追问。
- `新问题`：清空当前终端会话，另起话题；`重试`：重发失败的问题；`退出`：结束终端对话。
- 收藏与确认可像网页聊天一样输入，例如“收藏第1条”，再按后台提示明确确认。终端不绕过写入确认。

与网页共用本机后台、人物库、检索、解读及收藏，但终端与网页的对话会话独立。后台未运行时会隐藏启动；从当前用户的加密配置或环境变量读取密钥，未配置时隐藏询问，不保存明文。退出终端后后台仍能供网页使用。密钥不写入诊断日志。网页/桌面现按用户要求在本机 SQLite 保存历史问题和回答，终端共用查询接口也会保留查询历史；不做云端同步。

可选模型：`powershell -ExecutionPolicy Bypass -File .\terminal_chat.ps1 -Model deepseek-flash`。已有后台时不静默切换模型；要换模型，先关闭旧后台。跨平台可在装好依赖并配置环境变量后运行 `python terminal_chat.py`。

`python terminal_chat.py --no-start` 只连接现有后台；不启动新进程。API请求可能产生费用，展开详解也会请求模型，同一问题下重复查看已缓存详解不会额外生成。


## 新导航、历史与后台下载
首次输入居中；左上侧栏包含人物偏好、设置和本机历史，右上加号新建对话。人物联网查找在后台自动核验并下载，关闭弹窗也继续；同名人物先确认，下载后待资料校验再启用。详见 [说明](docs/NAVIGATION_AND_DISCOVERY.md)。


## 2026-10-24：0.3.0 发布准备

包含专属人物模式、顶部轮盘、历史与项目管理、置顶、归档恢复和本地目录关联。补齐桌面 Tk 资源与运行时 SSL 证书策略文件。长文入口仍为2000字符，下载 Skill 仍需审核。官网承担安装包分发，不代表已上线完整 Python 查询服务。详见 docs/PROJECT_ASSESSMENT_REPORT.md 和 reports/release-0.3.0-verified-tests.txt。
