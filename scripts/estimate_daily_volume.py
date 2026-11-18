"""Sample campus text in memory; persist aggregate metrics only, no post bodies."""
from pathlib import Path
import sys
import os
import json
import statistics
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'.runtime'))
os.environ['TIKTOKEN_CACHE_DIR']=str(ROOT/'private/tokenizer-cache')
import tiktoken
from campus.treehole import Treehole,TREE
from campus.config import load_config


def main():
    encoder=tiktoken.get_encoding('o200k_base')
    client=Treehole(load_config().get('treehole',{}))
    captured=datetime.now(timezone.utc)
    cutoff=captured.timestamp()-86400
    posts={}
    requested_pages=[]
    comments={}
    for page in range(1,102,5):
        result=client._json(client._request('GET',TREE+'/chapi/api/v3/hole/list_comments',params={
            'page':page,'limit':50,'comment_limit':3}))
        if result.get('code')!=20000:
            raise RuntimeError('Source retrieval failed; no content printed.')
        rows=result['data']['list']
        requested_pages.append(page)
        if not rows:
            break
        in_window=0
        for index,row in enumerate(rows):
            ts=float(row.get('timestamp') or 0)
            identity=str(row['pid'])
            if ts>=cutoff:
                in_window+=1
            if identity not in posts:
                text=str(row.get('text') or '')
                posts[identity]={'position':(page-1)*50+index,'timestamp':ts,'chars':len(text),
                    'tokens':len(encoder.encode(text,disallowed_special=())),
                    'replies':int(row.get('comment_total',row.get('reply',0)) or 0)}
            if ts>=cutoff:
                for comment in row.get('comment_list') or []:
                    cid=str(comment.get('cid',''))
                    if cid and cid not in comments:
                        text=str(comment.get('text') or '')
                        comments[cid]={'chars':len(text),'tokens':len(encoder.encode(text,disallowed_special=()))}
        print(json.dumps({'samplePage':page,'postsReturned':len(rows),'postsWithin24h':in_window}),flush=True)
        if in_window==0:
            break
    recent=[p for p in posts.values() if p['timestamp']>=cutoff]
    older=[p for p in posts.values() if 0<p['timestamp']<cutoff]
    if not recent:
        raise RuntimeError('No recent sample')
    lower=max(p['position'] for p in recent)+1
    upper=min((p['position'] for p in older if p['position']>=lower),default=None)
    n=(lower+upper)/2 if upper is not None else lower
    average=lambda key,rows:statistics.mean(p[key] for p in rows) if rows else 0
    post_chars=average('chars',recent);post_tokens=average('tokens',recent)
    reply_mean=average('replies',recent)
    comment_chars=average('chars',list(comments.values()));comment_tokens=average('tokens',list(comments.values()))
    report={'capturedAt':captured.isoformat(),'windowHours':24,'tokenizer':'o200k_base',
        'samplePages':requested_pages,'samplePosts24h':len(recent),'sampleCommentPreviews':len(comments),
        'dailyPostCountEstimate':n,'dailyPostCountBracket':[lower,upper],
        'postMeanChars':post_chars,'postMeanTokens':post_tokens,'postMedianChars':statistics.median(p['chars'] for p in recent),
        'meanRepliesPerNewPostAtCapture':reply_mean,'commentMeanChars':comment_chars,'commentMeanTokens':comment_tokens,
        'dailyPostCharsEstimate':n*post_chars,'dailyPostTokensEstimate':n*post_tokens,
        'repliesOnDailyNewPostsEstimate':n*reply_mean,
        'postAndAttachedCommentCharsEstimate':n*(post_chars+reply_mean*comment_chars),
        'postAndAttachedCommentTokensEstimate':n*(post_tokens+reply_mean*comment_tokens),
        'limitations':['Systematic page sampling, not a complete daily census.',
            'Comment lengths sampled from up to first three comments per thread.',
            'Counts attached replies on posts created within the window, not all comments written today on older threads.',
            'Counts text only, excluding images, JSON wrappers, prompts, output and reasoning.']}
    target=ROOT/'private/daily-volume-estimate.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
