# 教学网、树洞与接口

## 最少依赖的入口

不用先注册 MCP，也不用启动网页。所有 shell 命令从项目根执行：

```powershell
python manage.py status
python manage.py search "计算机系统" --sources treehole
python manage.py get "treehole:post:实际洞号"
python manage.py search "作业" --sources blackboard --offline
python scripts/find_high_comments.py --min-comments 1000 --pages 15
```

查询结果可能包含私人内容，按用户问题取必要范围。检索失败要检查 `warnings`，不把失败的空列表解释为无匹配。离线仅查已缓存内容，不是全站搜索。

## 指定洞与完整评论

完整 ID 是 `treehole:post:<数字洞号>`。无需先关键词搜到该洞。CLI 的 `get` 默认只读第一页；需要全部评论用 MCP 或本机 Python 调用：

```python
from campus.service import Campus
service = Campus()
pid = int(input('洞号: '))
result = service.get_document(f'treehole:post:{pid}', live=True, page=1, limit=30)
doc = result['document']
```

查看 `commentTotal`、`commentPage`、`commentPageSize`、`commentsComplete`。每页最多 30 条，正常分页 `page=2,3,...`，按评论 ID 去重，直到覆盖该次读取报告的总数；上游计数可能变化。`commentsComplete` 只在单页即可完整覆盖时为 true，后续页不是累计档案。公开方法最多 100 页；超过范围须说明缺口，不声称完整。当天批量采集使用专用采集器，见 daily.md。

缓存只保存最近读的一页评论。要总结全楼，必须把各页内容在本次任务中合并或持久化，不能反复覆盖缓存后只总结最后一页。详情不可用可能是删除、权限或会话问题，不能一概说二次验证没做。

## 关键词与评论数

普通 search 的空关键词只列本地缓存，不会拉树洞最新全量。树洞远程搜索可匹配评论中的词，即使预览未出现关键词，也不说明误命中。检索时可规划多个具体关键词，说明范围而非声称语义全站检索。

`find_high_comments.py` 逐页列出主帖，再按 `comment_total`/`reply` **严格大于**阈值筛选，按总评论数降序。参数：`--query`（可空）、`--start-page`、`--pages`（1–30）、`--min-comments`。读取 `scannedUniquePosts`、`scannedPages`、`stopReason`、`nextPage` 和 `warnings`；只有 `page_budget` 才按 nextPage 继续。不是官方全站历史排行榜。不能以收藏加权热度替代评论数。

不要使用 `page*limit >= total` 判断列表已结束；树洞接口的 total 和实际每页上限可能不一致。保留现有每秒请求间隔；遇验证/频控先停止并解释，不能开多个采集器绕过。

## 教学网

```powershell
python manage.py sync-blackboard
python manage.py search "课程关键词" --sources blackboard --offline
```

同步固定读取 `assignment`、`announcement`、`course`。检查 `results` 中每项 `ok`、`count`、错误，部分成功不可说三项全通。失败会保留旧数据，旧缓存不是本次成功证据。公告详情按搜索返回的完整 id 读取，不手拼公告 ID。

相对 DDL 保留 `deadlineText`；`dueAt=null` 不补造日期。课表不推断学期周次；`urlIsGeneric=true` 表示通用教学网入口，不是该作业深链。没有提交、选课或改成绩功能。

## MCP 与 HTTP（可选）

启动 MCP stdio：`python mcp_server.py`。其 stdout 是逐行 JSON-RPC，不要加日志。工具：

| 工具 | 参数示例 |
| --- | --- |
| campus_status | `{}` |
| campus_search | `{"query":"体测","sources":["treehole"],"limit":10,"page":1,"live_treehole":true}` |
| campus_get_document | `{"identity":"treehole:post:实际洞号","live":true,"page":1,"limit":30}` |
| campus_find_high_comments | `{"query":"","min_comments":1000,"start_page":1,"pages":15}` |
| campus_sync_blackboard | `{}` |

HTTP 是普通 REST，**不是 HTTP MCP**：本机 `http://127.0.0.1:8765`，需先运行 `python server.py`。各 `/api/v1/*` 接口需本机 `private/http-token` 的 Bearer，由代码内部读取，不回显。不能开放 CORS 或改为公开监听以方便 agent。完整路径、参数和结果字段见项目 `docs/API.md`，无须修改 dsh 全局配置即可使用 CLI/Python。
