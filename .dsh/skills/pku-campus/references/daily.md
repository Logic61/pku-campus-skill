# 全量文字日报与接续

## 范围必须先说明

默认统计 Asia/Shanghai **前一个自然日 00:00–24:00** 的新主帖，以及这些新帖在同一日内发表的可访问文字评论。**不含旧帖当天新增评论、图片/OCR、已删除和无权限内容**。这是现有采集器的覆盖范围，不可称全站全部流量。

如果用户明确要求包括旧洞的新评论，先说明现有采集器不支持，不能偷偷换定义。当天尚未结束只能做截至采集时的快报，不能与完整自然日混称。

## 采集

先查同一天是否已有进程在运行、`private/daily/treehole/<日期>/manifest.json` 是否完成；不要重复启动。可查看 `threads/*.json` 数量判断运行进度，不输出凭据。无运行进程且需要采集或补齐时：

```powershell
python scripts/collect_daily_treehole.py
```

默认使用北京时间昨天。补采某天可为采集器和后续阅读工具指定同一个 `--date YYYY-MM-DD`。采集器按日期扫描新帖、逐洞分页补评论，输出进度每100洞一次。运行可能数十分钟，正常等待并间隔报告进度；不要超时后另开同样任务。

原始检查点在 `private/daily/treehole/<日期>/threads/`；完整后生成 `batches/*.txt` 与 `manifest.json`。重复运行会复用满足日期和评论计数条件的完整检查点。`--max-threads` 仅烟测，永远不能用于全量日报。不要为让 complete 变 true 而提高错误容忍或跳过异常洞。

读取 manifest：`complete`、`listComplete`、`posts`、`commentsInWindow`、`incompleteThreads`、`missingCommentTimestamps`、`warnings`、`batches`、`finishedAt`。即使脚本退出0也必须检查这些字段；不完整时先看错误并合理重试。持续验证/频控失败停止，不反复登录。仍有缺口则标“部分采集”。

## 分批阅读与笔记

禁止仅看热帖或预览代替全量；不要用关键词统计假装完成语义阅读。只读取正文和必要元数据，不把原始 JSON 所有字段灌入上下文。批次可能从一篇长帖中间切开，结合前后批次保持上下文。

### 按偏好筛读

用户明确指定筛读偏好时，按其要求调整精读范围。例如可优先阅读具体实用信息、公共事务、创作或讨论较多的帖子，略读缺少可核验信息的个人闲聊。

- 略读也要为每个批次留覆盖记录（audit 需要），但不能把“筛读”写成“全量精读”；报告开头如实写“全量采集 + 按偏好筛选精读”。
- 用户未指定筛读偏好，或明确要求全量阅读时，逐批完整阅读。

为避免 shell 输出截断，使用 skill 内的辅助工具（路径相对项目根）：

```powershell
python .dsh/skills/pku-campus/scripts/daily_review.py status
python .dsh/skills/pku-campus/scripts/daily_review.py read --batch 001 --start 0 --chars 6000
```

`read` 先输出 SHA256、start、end、total，再输出该段完整文字。对照输出是否截断；需要时减小 chars。完整阅读后将提炼写入 `private/` 下的笔记文件，记下主题、原洞号、主要分歧、实用信息、未核实事项和轻松内容，不照抄联系方式。再用实际的 end 和 SHA256 登记该段：

```powershell
python .dsh/skills/pku-campus/scripts/daily_review.py note --batch 001 --start 0 --end 6000 --sha256 "实际哈希" --notes-file private/review-notes.md
```

然后从 read 返回的 end 继续直到 total，再处理 manifest 的下一批。每段笔记保存在 `batch-notes/`，带文件哈希和字符区间，方便上下文压缩/中断后接续。已登记区间不等于模型确实读过；登记只能在实际阅读与提炼后进行。

最终执行：

```powershell
python .dsh/skills/pku-campus/scripts/daily_review.py audit
```

它检查采集完成、各批次与当前哈希一致、笔记区间连续覆盖全文。`coverageComplete=true` 只证明文件覆盖记录，不能代替阅读质量判断；需确认笔记确为阅读所得。批次变化后旧哈希笔记不算完成；重读变化批次。

## 合成与交付

完成所有批次后，基于笔记写 `private/daily/treehole/<日期>/report.md`。默认约800–1500中文字、5–8个值得看的主题，并按实际内容调整：

- 开头给日期、采集时间、主帖/当日评论数量、批次与实际阅读方式，说明范围排除项与筛掉了什么。
- 每个主题说明讨论了什么、为什么值得注意，保留主要分歧。
- **洞号紧跟所描述的内容**。可用 `#洞号` 或带链接的 Markdown。
- 创作/抽象/反串/玩梗帖按用户偏好单独成节并适当多看，给足洞号。
- 合并刷屏、复读和跨洞续帖；不把一楼或某个热帖当全体学生观点，不将树洞负面发帖倾向泛化为全校情绪。
- 可含课程/生活实用线索与轻松片段。考试、体测、报销等未经官方核验的回复只作“待确认”，不给确定规则；不从匿名评论给医疗诊断或用药建议。
- 只有覆盖与阅读均完成才称“全量范围日报”。否则写 `report.partial.md` 并量化已读范围，不能用正常 report.md 暗示完成。

当日原文可能含第三方文章、歌词、长篇转帖：日报以概括为主，避免长段复制。

## token 统计

估算只能标估算；不要由抽样推断值冒充实测。可对最终 batches 使用模型实际 tokenizer 统计输入文字量，并单列分批指令、笔记合成、输出和工具元数据开销。字符数不是 token 数；实际费用由 dsh 当时模型计费决定，不从旧价格推算。
