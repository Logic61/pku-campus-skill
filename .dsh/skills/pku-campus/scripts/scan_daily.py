"""Scan a collected treehole day and surface what is worth reading.

Never calls a model or reads credentials. Two jobs:

  scan  -> write a markdown digest (high-comment threads, info-heavy posts,
           creative/absurd posts, plus a sample of low-value chatter) so the
           agent can pick what to read instead of reading every batch.
  show  -> print the full text (post + comments) of specific holes.

Usage (run from the project root):
  python .dsh/skills/pku-campus/scripts/scan_daily.py scan --date YYYY-MM-DD
  python .dsh/skills/pku-campus/scripts/scan_daily.py show --date YYYY-MM-DD --pid PID [PID ...]
"""
from pathlib import Path
import argparse
import json
import os
import random
import sys

INFO_KEYS = ("招聘", "宣讲", "实习", "内推", "报名", "截止", "讲座", "演出", "票",
             "考试", "期中", "期末", "体测", "报销", "医保", "公费", "转诊", "选课",
             "退课", "成绩", "绩点", "申请", "流程", "开通", "预约", "开放时间",
             "营业", "食堂", "快递", "打印", "洗衣机", "校园网", "网络", "自习",
             "图书馆", "游泳", "健身房", "面试", "笔试", "奖学金", "助学金",
             "贷款", "签证", "护照", "选调", "推免", "保研", "出国", "交换", "暑研",
             "截止日期", "时间地点", "抢课", "考场", "补测", "校医院", "挂号")
FUN_KEYS = ("悬赏", "本质", "同人", "小说", "连载", "接龙", "整活", "抽象",
            "反串", "钓鱼", "梗", "故事", "梦到", "起名", "汪汪", "woof",
            "骑士团", "克苏鲁", "恐怖", "诗", "日记", "锐评", "猫")


def root_path():
    explicit = os.environ.get("AWE_PKU_ROOT")
    candidates = [Path(explicit)] if explicit else []
    candidates += list(Path(__file__).resolve().parents)
    for path in candidates:
        if (path / "manage.py").is_file() and (path / "mcp_server.py").is_file():
            return path
    raise ValueError("找不到项目；设置 AWE_PKU_ROOT 或将 skill 保留在项目目录中。")


def load_threads(folder):
    rows = []
    for path in sorted((folder / "threads").glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        post = item.get("post") or {}
        comments = item.get("comments") or []
        rows.append({
            "pid": path.stem,
            "comments": len(comments),
            "text": str(post.get("text") or ""),
            "post": post,
            "raw": item,
        })
    return rows


def snippet(text, width=90):
    return text.replace("\n", " / ").replace("\r", "")[:width]


def scan(folder, args):
    rows = load_threads(folder)
    if not rows:
        raise ValueError("没有找到任何 threads/*.json，先完成采集。")
    rows.sort(key=lambda r: (-r["comments"], r["pid"]))
    total_comments = sum(r["comments"] for r in rows)
    buckets = {"0": 0, "1-4": 0, "5-9": 0, "10-19": 0, "20-49": 0, "50+": 0}
    for r in rows:
        n = r["comments"]
        if n == 0:
            buckets["0"] += 1
        elif n < 5:
            buckets["1-4"] += 1
        elif n < 10:
            buckets["5-9"] += 1
        elif n < 20:
            buckets["10-19"] += 1
        elif n < 50:
            buckets["20-49"] += 1
        else:
            buckets["50+"] += 1

    hot = [r for r in rows if r["comments"] >= args.hot]
    info = [r for r in rows if any(k in r["text"] for k in INFO_KEYS) and r["comments"] < args.hot]
    fun = [r for r in rows if any(k in r["text"] for k in FUN_KEYS) and r["comments"] < args.hot]
    picked = {r["pid"] for r in hot} | {r["pid"] for r in info} | {r["pid"] for r in fun}
    rest = [r for r in rows if r["pid"] not in picked]
    random.seed(args.seed)
    sample = random.sample(rest, min(args.sample, len(rest)))

    lines = [f"# 采集扫描 · {args.date}", "",
             f"- 帖子数：{len(rows)}；评论总数：{total_comments}",
             f"- 评论数分布：{buckets}",
             f"- 高评论（≥{args.hot} 条）：{len(hot)} 帖；信息类关键词命中（低评论）：{len(info)} 帖；"
             f"创作/抽象类命中（低评论）：{len(fun)} 帖；其余抽样：{len(sample)} 帖",
             "", "## 高评论帖（优先精读，看完整评论）", ""]
    for r in hot:
        lines.append(f"- #{r['pid']} ({r['comments']} 条) {snippet(r['text'])}")
    lines += ["", "## 信息类低评论帖（可能是硬信息，看原文+少量评论）", ""]
    for r in sorted(info, key=lambda r: r["pid"]):
        lines.append(f"- #{r['pid']} ({r['comments']} 条) {snippet(r['text'])}")
    lines += ["", "## 创作/抽象类低评论帖（有意思的看原文）", ""]
    for r in sorted(fun, key=lambda r: r["pid"]):
        lines.append(f"- #{r['pid']} ({r['comments']} 条) {snippet(r['text'])}")
    lines += ["", "## 低评论抽样（只扫标题，确认没有埋没的宝）", ""]
    for r in sample:
        lines.append(f"- #{r['pid']} ({r['comments']} 条) {snippet(r['text'], 70)}")
    lines.append("")

    out = folder / "work" / "scan.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"scan": str(out), "posts": len(rows), "comments": total_comments,
            "hot": len(hot), "info": len(info), "fun": len(fun), "sample": len(sample)}


def show(folder, pids):
    threads = {r["pid"]: r for r in load_threads(folder)}
    missing = [p for p in pids if p not in threads]
    for pid in pids:
        item = threads.get(pid)
        if not item:
            print(f"#{pid} 不存在", file=sys.stderr)
            continue
        print(f"\n{'=' * 60}\n【树洞 #{pid}】 评论 {item['comments']} 条\n主帖：{item['text'].strip()}\n")
        for c in item["raw"].get("comments") or []:
            text = str(c.get("text") or "").replace("\n", " ")
            print(f"  - {text[:220]}")
    if missing:
        raise ValueError(f"缺少洞号：{','.join(missing)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "show"):
        child = sub.add_parser(name)
        child.add_argument("--date", required=True)
        if name == "scan":
            child.add_argument("--hot", type=int, default=20)
            child.add_argument("--sample", type=int, default=40)
            child.add_argument("--seed", type=int, default=7)
        else:
            child.add_argument("--pid", nargs="+", required=True)
    args = parser.parse_args()
    folder = root_path() / "private/daily/treehole" / args.date
    if args.command == "scan":
        print(json.dumps(scan(folder, args), ensure_ascii=False, indent=2))
    else:
        show(folder, args.pid)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
