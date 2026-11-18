"""Local batch reader and coverage ledger. Never calls a model or reads credentials."""
from pathlib import Path
import argparse
from datetime import datetime, timedelta, timezone, date
import hashlib
import json
import os
import re
import sys


def root_path():
    explicit = os.environ.get('AWE_PKU_ROOT')
    candidates = [Path(explicit)] if explicit else []
    candidates += list(Path(__file__).resolve().parents)
    for path in candidates:
        if (path / 'manage.py').is_file() and (path / 'mcp_server.py').is_file():
            return path
    raise ValueError('找不到项目；设置 AWE_PKU_ROOT 或将 skill 保留在项目目录中。')


def read_packet(folder, batch):
    if not re.fullmatch(r'[0-9]{3,6}', batch):
        raise ValueError('batch 应是三至六位编号，例如001。')
    path = folder / 'batches' / (batch + '.txt')
    content = path.read_text(encoding='utf-8')
    digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
    return path, content, digest


def coverage(folder, manifest):
    details = []
    for batch in manifest.get('batches', []):
        # The manifest path is informational; resolve only the local basename.
        basename = str(batch['path']).replace('\\', '/').rsplit('/', 1)[-1]
        identity = Path(basename).stem
        _, content, digest = read_packet(folder, identity)
        intervals = []
        for path in (folder / 'batch-notes').glob(identity + '.*.json'):
            entry = json.loads(path.read_text(encoding='utf-8'))
            if entry.get('sha256') == digest and entry.get('notes', '').strip():
                left, right = entry.get('start'), entry.get('end')
                if (isinstance(left, int) and isinstance(right, int)
                        and 0 <= left < right <= len(content)):
                    intervals.append((left, right))
        cursor = 0
        gaps = []
        for left, right in sorted(intervals):
            if left > cursor:
                gaps.append([cursor, left])
            cursor = max(cursor, right)
        if cursor < len(content):
            gaps.append([cursor, len(content)])
        details.append({'batch': identity, 'sha256': digest, 'chars': len(content),
                        'covered': len(content) - sum(b-a for a,b in gaps), 'gaps': gaps})
    return details


def run(args):
    date.fromisoformat(args.date)
    folder = root_path() / 'private/daily/treehole' / args.date
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else None
    if args.command == 'status':
        return {'date': args.date, 'checkpointThreads': len(list((folder / 'threads').glob('*.json'))),
                'manifestPresent': manifest is not None,
                'collection': {k: manifest.get(k) for k in (
                    'complete', 'listComplete', 'posts', 'commentsInWindow',
                    'incompleteThreads', 'missingCommentTimestamps', 'warnings', 'finishedAt')}
                    if manifest else None,
                'batches': len(manifest.get('batches', [])) if manifest else 0,
                'note': '无manifest可能仍在采集，也可能已中断；先检查运行进程，不能据此认定完成。'}
    if not manifest:
        raise ValueError('尚无manifest，请先等待采集完成或检查中断。')
    if args.command == 'audit':
        details = coverage(folder, manifest)
        complete = bool(manifest.get('complete') and manifest.get('listComplete')
                        and not manifest.get('incompleteThreads')
                        and not manifest.get('missingCommentTimestamps')
                        and (details or manifest.get('posts') == 0)
                        and all(not item['gaps'] for item in details))
        return {'date': args.date, 'collectionComplete': manifest.get('complete', False),
                'coverageComplete': complete, 'batches': details,
                'note': '区间记录只能证明笔记覆盖，不能证明模型确实阅读或提炼质量。'}
    _, content, digest = read_packet(folder, args.batch)
    if not 0 <= args.start < len(content):
        raise ValueError('start不在批次文字范围内。')
    if args.command == 'read':
        if not 1 <= args.chars <= 24000:
            raise ValueError('chars应在1至24000之间。')
        end = min(args.start + args.chars, len(content))
        print(json.dumps({'batch': args.batch, 'sha256': digest, 'start': args.start,
                          'end': end, 'total': len(content)}, ensure_ascii=False))
        print(content[args.start:end])
        return None
    if args.sha256 != digest:
        raise ValueError('批次哈希已变化，请重新阅读，不登记旧笔记。')
    if not args.start < args.end <= len(content):
        raise ValueError('end应大于start且不超过全文长度。')
    notes = Path(args.notes_file).read_text(encoding='utf-8').strip()
    if not notes:
        raise ValueError('笔记为空，不能登记。')
    entry = {'batch': args.batch, 'sha256': digest, 'start': args.start, 'end': args.end,
             'notes': notes, 'recordedAt': datetime.now(timezone.utc).isoformat()}
    target = folder / 'batch-notes' / f'{args.batch}.{args.start}-{args.end}.json'
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    return {'recorded': str(target), 'start': args.start, 'end': args.end, 'sha256': digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    yesterday = (datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=1)).isoformat()
    for command in ('status', 'read', 'note', 'audit'):
        child = sub.add_parser(command)
        child.add_argument('--date', default=yesterday)
        if command in ('read', 'note'):
            child.add_argument('--batch', required=True)
            child.add_argument('--start', type=int, default=0)
        if command == 'read':
            child.add_argument('--chars', type=int, default=6000)
        if command == 'note':
            child.add_argument('--end', type=int, required=True)
            child.add_argument('--sha256', required=True)
            child.add_argument('--notes-file', required=True)
    try:
        result = run(parser.parse_args())
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'error': '日期、批次、哈希、区间、笔记或数据文件不匹配；检查参数及采集状态。'}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
