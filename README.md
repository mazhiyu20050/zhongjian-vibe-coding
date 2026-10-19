# 众见 · Zhongjian

人物 Skill 路由 + 本地 RAG 的观点查询 Agent。输入困惑，从十二位人物的本地原著或已核验公开短引中检索，生成不同视角的解答并校验引用。

## 启动（Python 3.11+）

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

本次提交排除 API 密钥、Windows 加密密钥文件、收藏数据库、运行时日志以及私人聊天截图。运行时问题和候选资料会发送到配置的 DeepSeek 服务；对话默认只保留在进程内存，收藏由用户确认后写入本机 SQLite。原文匹配校验不能证明解读一定正确；语料未完成逐段校勘。当前不支持向量语义召回，历史对话话题切分仍可能影响相关性，模型的排序、语气和建议需持续评估。

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
