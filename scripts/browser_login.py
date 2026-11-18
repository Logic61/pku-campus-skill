import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from campus.browser_login import run_browser_login

parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True,choices=['treehole','blackboard','portal'])
parser.add_argument('--job',required=True)
args=parser.parse_args()
run_browser_login(args.source,args.job)
