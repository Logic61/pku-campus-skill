# 本机安装与故障排查

## 安装与发现

从项目根目录启动 `dsh`，filesystem skill provider 可在 `.dsh/skills/pku-campus/SKILL.md` 发现本项目的 skill。若从其他项目启动，可切回 AWE PKU 项目，或明确让 agent 读取此 skill 并在 AWE PKU 根目录执行命令。

首次使用先安装 `requirements.txt`，再用 `python manage.py init` 生成空白本地配置。用户决定是否在 `private/config.toml` 启用 `agent.allow_private`。安装 Chrome 登录依赖、配置 pku3b 和使用 MCP 的方法见项目 README。

## 登录态

官方登录入口是工作台 http://127.0.0.1:8765/ 的“在官方页面登录”。需启动 `python server.py`。由用户在独立 **Chrome** 完成 IAAA/二次验证，再回工作台点“完成登录并保存会话”。树洞、教学网和门户课表是不同目标，教学网已登录不等于门户课表已登录。

Chrome 专用资料位于 `private/browser-profiles/`，不是日常 Chrome 资料。保存会话前用实际查询接口验证；看到浏览器已登录但保存失败时，检查接口错误分类，不直接说用户没做二次验证。

树洞浏览器会话包含 Bearer token、网页设备 UUID、User-Agent 和限定来源的 Cookie。检索时复用 `campus/treehole.py`。六位手机令牌用于登录验证，在官方页面或交互终端输入。

错误先分类：`needs_login`/401/403、`needs_verification`、网络超时、证书、上游结构变化是不同问题。网络错误不重置会话；上游 schema 异常不当零条结果；失败保留旧缓存。不要关闭私人访问开关或修改 allow_private 来绕过用户选择。

如果需要接续日报，检查目标日期的本机 manifest 和批次笔记，流程见 [日报参考](daily.md)。PKUKnow 抓取失败时，可用 [活动参考](activities.md) 中的官方来源继续核验。
