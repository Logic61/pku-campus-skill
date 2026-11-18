# 燕园一处 · AWE PKU

`pku-campus` 是一个在本机运行的北大校园信息 skill。它可以检索教学网作业、公告和课表，搜索树洞和分页读取评论，按总评论数筛洞，采集与核验树洞日报，以及查找并核验校园活动。项目还提供网页工作台、CLI、MCP 和 HTTP 接口，共用本机连接器。

## 安装与试用

下载或克隆整个仓库，在仓库根目录运行以下命令。需要 Python 3.11 或更新版本。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py init
python manage.py status
python manage.py search "网球" --sources activities --offline
```

macOS 和 Linux 用 `python3 -m venv .venv` 创建环境，再用 `source .venv/bin/activate` 激活。PowerShell 若限制激活脚本，可以用 `.\.venv\Scripts\python.exe` 直接执行 Python 命令。

公开活动搜索无需账号，随仓库附带一份 PKUKnow 首页快照，内容为公开标题、发布单位、发布时间和原文链接。推荐具体活动时，应回原文确认实际活动时间和报名状态。

运行 `python server.py`，然后在浏览器打开 [本机工作台](http://127.0.0.1:8765/)。请在自己的电脑上运行，服务监听本机地址。

## 配置自己的账号

`python manage.py init` 从空白模板生成本地配置。重复执行会保留已有配置。

| 公开模板 | 本地文件 | 填写内容 |
| --- | --- | --- |
| [config.example.toml](config.example.toml) | `private/config.toml` | 连接器设置，以及可选的树洞账号或 Bearer token |
| [pku3b.example.toml](pku3b.example.toml) | `private/pku3b.toml` | 使用密码登录教学网时填写自己的账号 |

新配置默认关闭通过工作台、CLI、HTTP 和 MCP 进行的私人检索和同步。使用这些功能前，在 `private/config.toml` 的 `[agent]` 下将 `allow_private` 设为 `true`。

- **在官方网页登录**：安装 `python -m pip install -r requirements-browser.txt`，并准备 Google Chrome。启动工作台后，选择树洞、教学网或课表门户的“在官方页面登录”。在弹出的专用 Chrome 窗口完成验证，再回工作台点击“完成登录并保存会话”。教学网与课表门户可分别登录。
- **同步教学网**：Windows x64 可运行 `python scripts/install_pku3b.py` 安装项目内的 pku3b 0.16.1。其他平台从 [pku3b Releases](https://github.com/sshwy/pku3b/releases) 安装对应版本，在本地配置的 `blackboard.executable` 填写可执行文件路径。保存浏览器会话或配置 CLI 账号后，运行 `python manage.py sync-blackboard`。需要六位手机令牌时，在本机终端执行 `python manage.py sync-blackboard --otp`。令牌不会写入配置，调用 pku3b 时会短暂出现在子进程参数中。
- **用终端登录树洞**：运行 `python manage.py login-treehole`，按终端提示输入账号密码和所需验证码。也可以在本地 `[treehole]` 下填入现有 Bearer token。涉及短信验证时，请在官方网页完成。

## 在 Agent 中使用

安装 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 后，从仓库根目录激活 Python 环境并运行 `dsh`。项目内的 skill 入口是 [SKILL.md](.dsh/skills/pku-campus/SKILL.md)。其他能运行本机命令的 agent 可以直接读取这个文件，工作目录设为仓库根目录。

可以这样问：

- “用 pku-campus 查看教学网作业，标出上次同步时间。”
- “用 pku-campus 找总评论数超过 1000 的树洞，说明查了多少页。”
- “用 pku-campus 做昨天的树洞日报，核对采集范围和阅读覆盖。”
- “推荐未来一周还能报名的校园活动，附原文。”

### MCP 和 HTTP

MCP 使用 stdio，由客户端启动 `mcp_server.py`，无需先启动网页。支持状态查询、统一搜索、详情与分页评论、按评论数筛洞和教学网只读同步。配置时请使用各自机器上 Python 和脚本的绝对路径，可参考 [codex-mcp.example.toml](codex-mcp.example.toml)。

例如在已激活虚拟环境的 PowerShell 中注册到 Codex：

```powershell
codex mcp add awe_pku -- (Get-Command python).Source (Join-Path $PWD 'mcp_server.py')
```

普通应用可以使用本机 HTTP 接口，详见 [API 文档](docs/API.md)。

## 本地数据与发布范围

- `private/` 保存账号配置、Cookie、token、Chrome 专用资料、SQLite、树洞原文和日报。Git 会忽略整个目录。部分文件以明文存储，由本机账户权限保护。
- 仓库按 [发布清单](.gitignore) 放行源码、文档、空白配置模板和公开活动快照。虚拟环境、下载的工具、本机研究材料、课程归档和截图也在忽略范围内。
- 启用私人检索后，返回给 agent 的正文和评论会进入该 agent 的上下文。AWE PKU 本身不发起额外的模型 API 调用。切换账号时，请先备份并移走旧账号的登录会话和本地缓存。
- 教学网接口只读。公告正文按需读取，课表门户可能需要单独登录。相对截止时间保留原文。树洞日报默认覆盖前一个北京时间自然日的新帖及这些帖当天的可访问文字评论，具体范围见 [日报参考](.dsh/skills/pku-campus/references/daily.md)。

## 开发与验证

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
```

`campus/` 为连接器和存储，`web/` 为无需构建的网页，`scripts/` 提供安装、采集等本机工具。可选的文字量估算脚本 `scripts/estimate_daily_volume.py` 另需 `tiktoken`。

校园公开数据来自 [PKUKnow](https://pkuknow.cn/)，教学网使用独立的 [pku3b](https://github.com/sshwy/pku3b) 客户端。树洞接口参考 [树洞检索项目](https://github.com/SunVapor/pku-treehole-search-agent)，工作台方向参考 [PKU Captain](https://github.com/RizzoHou/pku-captain)。
