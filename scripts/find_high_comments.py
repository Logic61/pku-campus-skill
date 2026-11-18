"""Bounded read-only comment-count filter, reusing the local treehole session."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from campus.config import CampusError
from campus.service import Campus

parser=argparse.ArgumentParser()
parser.add_argument('--query',default='')
parser.add_argument('--min-comments',type=int,default=100)
parser.add_argument('--start-page',type=int,default=1)
parser.add_argument('--pages',type=int,default=15)
args=parser.parse_args()
try:
    result=Campus().high_comment_posts(query=args.query,min_comments=args.min_comments,start_page=args.start_page,pages=args.pages)
    result['items']=[{k:doc.get(k) for k in ('id','sourceId','commentTotal','title','url','publishedAt','fetchedAt')} for doc in result['items']]
    sys.stdout.buffer.write((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
except CampusError as exc:
    sys.stdout.buffer.write(json.dumps({'error':exc.as_dict()},ensure_ascii=False).encode('utf-8'))
    raise SystemExit(1)
