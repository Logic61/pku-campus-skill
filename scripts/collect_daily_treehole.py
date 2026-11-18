"""Collect yesterday's new threads and all retrievable comments into local batches.

No model calls. Credentials never enter the output. Raw text stays under private/.
"""
from pathlib import Path
import argparse
from datetime import datetime,date,time,timedelta,timezone
import json
import sys
import time as runtime_clock

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from campus.config import load_config,CampusError
from campus.treehole import Treehole,TREE

SHANGHAI=timezone(timedelta(hours=8))


def day_window(day):
    start=datetime.combine(date.fromisoformat(day),time.min,SHANGHAI)
    return start.timestamp(),(start+timedelta(days=1)).timestamp()


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)


def in_window(item,start,end):
    try:
        return start<=float(item.get('timestamp'))<end
    except (ValueError,TypeError):
        return False


def retrieve_comments(client,post,max_pages):
    reported=int(post.get('comment_total',post.get('reply',0)) or 0)
    if reported==0:
        return [],True,0
    comments={}
    total=reported
    for page in range(1,max_pages+1):
        data=client._json(client._request('GET',f'{TREE}/api/pku_comment_v3/{post["pid"]}',params={'page':page,'limit':20,'sort':'asc'}))
        payload=data.get('data')
        if data.get('success') not in (True,'true') or not isinstance(payload,dict) or not isinstance(payload.get('data'),list):
            raise CampusError('comment_schema','评论返回格式异常，不计为零评论。')
        rows=payload['data']
        total=int(payload.get('total',total))
        new_count=0
        for row in rows:
            identity=str(row.get('cid',''))
            if identity and identity not in comments:
                comments[identity]=row;new_count+=1
        if len(comments)>=total:
            return list(comments.values()),True,total
        if not rows or new_count==0:
            return list(comments.values()),False,total
    return list(comments.values()),False,total


def batch_text(threads,start,end,size=24000):
    batches=[]
    current=''
    for thread in threads:
        post=thread['post']
        header=f'\n\n【树洞 #{post["pid"]}】https://treehole.pku.edu.cn/web/#/hole/{post["pid"]}\n'
        body=header+'主帖：'+str(post.get('text') or '')+'\n'
        for comment in thread['comments']:
            if in_window(comment,start,end):
                body+=f"评论 {comment.get('cid','')}（{comment.get('name','匿名')}）：{comment.get('text') or ''}\n"
        while body:
            remaining=size-len(current)
            if remaining==0:
                batches.append(current);current='';remaining=size
            current+=body[:remaining]
            body=body[remaining:]
    if current:
        batches.append(current)
    return batches


def collect(day,max_list_pages=300,max_comment_pages=200,max_threads=None,max_runtime_seconds=None,resume_list=False):
    run_started=runtime_clock.monotonic()
    start,end=day_window(day)
    folder=ROOT/'private/daily/treehole'/day
    folder.mkdir(parents=True,exist_ok=True)
    client=Treehole(load_config().get('treehole',{}));client.require_session()
    manifest={'date':day,'timezone':'Asia/Shanghai','scope':'当日新主帖及其截至当日结束的可访问文字评论；不含旧帖当日新增评论和图片内容。',
              'startedAt':datetime.now(SHANGHAI).isoformat(),'complete':False,'listComplete':False,
              'posts':0,'commentsInWindow':0,'missingCommentTimestamps':0,'warnings':[],'batches':[]}
    posts={};seen=set();old_pages=0
    list_checkpoint=folder/'post-list.json'
    if resume_list and list_checkpoint.exists():
        saved=json.loads(list_checkpoint.read_text(encoding='utf-8'))
        if saved.get('date')==day and saved.get('listComplete') and saved.get('snapshotAt',0)>=end:
            posts={str(row['pid']):row for row in saved['posts']}
            manifest.update(listComplete=True,listPagesRead=saved['listPagesRead'],listFromCheckpoint=True)
    for page in ([] if manifest['listComplete'] else range(1,max_list_pages+1)):
        try:
            d=client._json(client._request('GET',TREE+'/chapi/api/v3/hole/list_comments',params={'page':page,'limit':50,'comment_limit':0}))
            if d.get('code')!=20000 or not isinstance(d.get('data',{}).get('list'),list):
                raise CampusError('list_failed','主帖列表读取失败。')
            rows=d['data']['list']
            if not rows:
                manifest['listComplete']=True;break
            new_ids={str(row['pid']) for row in rows}-seen
            if not new_ids:
                manifest['warnings'].append({'code':'repeated_page','page':page});break
            seen.update(new_ids)
            for row in rows:
                if in_window(row,start,end):posts[str(row['pid'])]=row
            old_pages=old_pages+1 if all(float(row.get('timestamp') or 0)<start for row in rows) else 0
            manifest['listPagesRead']=page
            if page%10==0:
                print(json.dumps({'stage':'list','pages':page,'posts':len(posts)}),flush=True)
            if old_pages>=2:
                manifest['listComplete']=True;break
            if max_threads and len(posts)>=max_threads:
                break
        except CampusError as exc:
            if exc.code in ('needs_login','invalid_session','rate_limited','upstream_schema','network_error'):
                manifest['warnings'].append({'page':page,**exc.as_dict()})
                write_json(folder/'manifest.json',manifest)
                raise
            manifest['warnings'].append({'page':page,**exc.as_dict()});break
    if not manifest['listComplete']:
        manifest['warnings'].append({'code':'partial_list','message':'尚未读取完整日期范围，不能称为全量日报。'})
    selected=sorted(posts.values(),key=lambda p:(p['timestamp'],p['pid']))
    if manifest['listComplete']:
        write_json(list_checkpoint,{'date':day,'listComplete':True,'listPagesRead':manifest['listPagesRead'],
            'snapshotAt':datetime.now(timezone.utc).timestamp(),'posts':selected})
    if max_threads:selected=selected[:max_threads]
    threads=[];incomplete=0
    for post in selected:
        if max_runtime_seconds and runtime_clock.monotonic()-run_started>=max_runtime_seconds:
            manifest['warnings'].append({'code':'runtime_checkpoint','message':'本轮时间预算已到，已保存检查点；需续采后才能生成日报。'})
            break
        checkpoint=folder/'threads'/f'{post["pid"]}.json'
        try:
            cached=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else None
            if cached and cached.get('unavailable') and cached.get('snapshotAt',0)>=end:
                item=cached
                manifest['warnings'].append({'pid':str(post['pid']),'code':'unavailable','message':'该洞评论已核验仍不可访问或返回无有效列表，保留缺口，不重复请求。'})
            elif cached and cached.get('complete') and cached.get('snapshotAt',0)>=end and cached.get('reportedComments')==int(post.get('comment_total',post.get('reply',0)) or 0):
                item=cached
            else:
                comments,complete,total=retrieve_comments(client,post,max_comment_pages)
                item={'post':post,'comments':comments,'complete':complete,'reportedComments':total,'snapshotAt':datetime.now(timezone.utc).timestamp()}
                write_json(checkpoint,item)
            threads.append(item)
            if not item['complete']:incomplete+=1
        except CampusError as exc:
            if exc.code in ('needs_login','invalid_session','rate_limited','upstream_schema','network_error'):
                manifest.update(posts=len(selected),processedThreads=len(threads),incompleteThreads=incomplete+1)
                manifest['warnings'].append({'pid':str(post['pid']),**exc.as_dict()})
                write_json(folder/'manifest.json',manifest)
                raise
            incomplete+=1
            threads.append({'post':post,'comments':[],'complete':False})
            manifest['warnings'].append({'pid':str(post['pid']),**exc.as_dict()})
        if len(threads)%100==0:
            print(json.dumps({'stage':'comments','processedThreads':len(threads),'totalThreads':len(selected)}),flush=True)
    packets=batch_text(threads,start,end)
    for index,text in enumerate(packets,1):
        path=folder/'batches'/f'{index:03d}.txt'
        path.parent.mkdir(exist_ok=True)
        path.write_text(text,encoding='utf-8')
        manifest['batches'].append({'path':str(path),'chars':len(text)})
    manifest.update({'posts':len(threads),'commentsInWindow':sum(in_window(c,start,end) for t in threads for c in t['comments']),
        'missingCommentTimestamps':sum(c.get('timestamp') is None for t in threads for c in t['comments']),
        'incompleteThreads':incomplete,'unprocessedThreads':len(selected)-len(threads),
        'totalThreads':len(selected),'complete':manifest['listComplete'] and incomplete==0 and max_threads is None and len(threads)==len(selected),
        'finishedAt':datetime.now(SHANGHAI).isoformat()})
    if manifest['missingCommentTimestamps']:
        manifest['complete']=False
    write_json(folder/'manifest.json',manifest)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--date',default=(datetime.now(SHANGHAI).date()-timedelta(days=1)).isoformat())
    parser.add_argument('--max-list-pages',type=int,default=300)
    parser.add_argument('--max-comment-pages',type=int,default=200)
    parser.add_argument('--max-threads',type=int,default=None,help='Diagnostic partial run only; never marks full coverage.')
    parser.add_argument('--max-runtime-seconds',type=int,default=None,help='Save a partial checkpoint after this runtime; resume the same date to finish.')
    parser.add_argument('--resume-list',action='store_true',help='Reuse a complete post-midnight list checkpoint for the same date.')
    args=parser.parse_args()
    try:
        result=collect(args.date,args.max_list_pages,args.max_comment_pages,args.max_threads,args.max_runtime_seconds,args.resume_list)
        sys.stdout.buffer.write((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    except CampusError as exc:
        sys.stderr.buffer.write(json.dumps({'error':exc.as_dict()},ensure_ascii=False).encode('utf-8'))
        raise SystemExit(1)
