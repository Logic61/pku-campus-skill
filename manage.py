"""Local setup, login, diagnostics and retrieval; never prints credentials."""
import argparse
import getpass
import json
import shutil
import sys
from campus.config import ROOT, CampusError, load_config
from campus.service import Campus
from campus.treehole import Treehole


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command',required=True)
    for name in ('init','status','login-treehole'):
        commands.add_parser(name)
    sync = commands.add_parser('sync-blackboard')
    sync.add_argument('--otp',action='store_true',help='每类数据读取前在终端输入六位 OTP，不保存')
    search = commands.add_parser('search')
    search.add_argument('query')
    search.add_argument('--sources',nargs='+',default=['activities','blackboard','treehole'])
    search.add_argument('--offline',action='store_true')
    get = commands.add_parser('get')
    get.add_argument('identity')
    get.add_argument('--offline',action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            private = ROOT / 'private'
            private.mkdir(exist_ok=True)
            for template,target in [('config.example.toml','config.toml'),('pku3b.example.toml','pku3b.toml')]:
                if not (private / target).exists():
                    shutil.copyfile(ROOT / template,private / target)
            result = {'ok':True,'message':'已创建空白本地配置；现有配置不会覆盖。填写 private/config.toml 与 private/pku3b.toml。'}
        elif args.command == 'login-treehole':
            config = load_config().get('treehole',{})
            client = Treehole(config)
            if config.get('token'):
                result = client.check_login()
            else:
                username = config.get('username') or input('树洞学号: ').strip()
                password = config.get('password') or getpass.getpass('门户密码: ')
                result = client.login(username,password)
            if result['state'] == 'needs_mobile_token':
                result = client.verify_mobile(getpass.getpass('六位手机令牌（不会回显）: ').strip())
        else:
            service = Campus()
            if args.command == 'status':
                result = service.status()
            elif args.command == 'sync-blackboard':
                provider = (lambda kind: getpass.getpass(f'{kind} 六位手机令牌: ').strip()) if args.otp else None
                result = service.sync_blackboard(otp_provider=provider)
            elif args.command == 'search':
                result = service.search(args.query,sources=args.sources,live_treehole=not args.offline)
            else:
                result = service.get_document(args.identity,live=not args.offline)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result.get('ok') is False:
            return 1
        return 0
    except CampusError as exc:
        print(json.dumps({'error':exc.as_dict()},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
