"""Read-only pku3b 0.16.x adapter. Never accepts a caller-supplied command."""
import json
import os
import re
import shutil
import subprocess
import tomllib
from .config import CampusError, local_path
from .store import now

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
HEADER = re.compile(r'^(?:\[\s*\d+\]\s*)?(?P<course>.+?) > (?P<title>.+?) (?P<id>[0-9a-f]{1,16})\s*$', re.M)


def base_doc(identity, title, course, text, kind):
    return {'id': f'blackboard:{kind}:{identity}', 'sourceId': identity,
            'source':'blackboard', 'kind':kind, 'title':title, 'course':course,
            'text':text, 'url':'https://course.pku.edu.cn/', 'urlIsGeneric':True,
            'publishedAt':None, 'dueAt':None, 'fetchedAt':now(), 'visibility':'private'}


def parse_list(output, kind):
    text = ANSI.sub('', output).replace('\r', '')
    matches = list(HEADER.finditer(text))
    total = re.search(r'(?:未完成作业|所有作业 \(包括已完成\)|课程公告)\s*\((\d+)\)', text)
    if total is None or int(total[1]) != len(matches):
        raise CampusError('unsupported_output', 'pku3b 输出格式不匹配；未覆盖上次数据，请核对版本和登录状态。')
    docs = []
    for index, match in enumerate(matches):
        content = text[match.end():matches[index+1].start() if index+1 < len(matches) else len(text)].strip()
        title = match['title']
        doc = base_doc(match['id'], title, match['course'], content, kind)
        if kind == 'assignment':
            # pku3b emits relative durations, not an authoritative absolute date.
            status = re.search(r' \((.*)\)$', title)
            doc['deadlineText'] = status[1] if status else None
            doc['completed'] = bool(status and status[1].startswith('已完成:'))
            if status:
                doc['title'] = title[:status.start()]
            doc['timeNote'] = 'deadlineText 为采集时的上游原始状态，dueAt 未知；请回教学网核对精确时间。'
        else:
            doc['detailLoaded'] = False
        docs.append(doc)
    return docs


def parse_timetable(output):
    try:
        data = json.loads(output)
        slots = data['course']
        if not isinstance(slots, list):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise CampusError('unsupported_output', '课表 JSON 结构不匹配，未覆盖旧课表。') from None
    docs = []
    for slot_index, slot in enumerate(slots, 1):
        if not isinstance(slot, dict):
            continue
        for day in ('mon','tue','wed','thu','fri','sat','sun'):
            entry = slot.get(day)
            if not isinstance(entry, dict) or not entry.get('courseName'):
                continue
            text = re.sub('<[^>]+>', ' ', str(entry['courseName']))
            doc = base_doc(f'{day}-{slot_index}', text.split('(主)')[0].strip(), '', text, 'course')
            doc.update({'weekday':day, 'slot':slot_index})
            docs.append(doc)
    return docs


class Blackboard:
    def __init__(self, config):
        self.config = config

    def executable(self):
        value = self.config.get('executable', 'bin/pku3b.exe')
        path = local_path(value)
        return str(path) if path.is_file() else shutil.which(value)

    def status(self):
        if not self.config.get('enabled', False):
            return {'state':'disabled', 'message':'教学网连接器未启用。'}
        if not self.executable():
            return {'state':'missing_dependency', 'message':'未找到 pku3b；请运行安装脚本。'}
        from .config import ROOT
        if (ROOT / 'private/blackboard-browser-session.json').is_file():
            return {'state':'configured','message':'已保存浏览器登录会话，实际读取时核验；课表门户需单独登录。'}
        try:
            path = local_path(self.config.get('config_file','private/pku3b.toml'))
            cfg = tomllib.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            return {'state':'needs_config', 'message':'请配置 private/pku3b.toml。'}
        if not cfg.get('username') or not (cfg.get('password') or cfg.get('secret_backend') == 'keyring'):
            return {'state':'needs_credentials', 'message':'请在 private/pku3b.toml 填入账号密码，或配置系统钥匙串。'}
        return {'state':'configured', 'message':'已配置，尚需同步验证登录；OTP 请在本机终端完成。'}

    def run(self, operation, identity=None, otp=''):
        allowed = {'assignment':['assignment','list','--all'],
                   'announcement':['announcement','list'],
                   'course':['coursetable','--raw']}
        if operation == 'announcement_detail' and re.fullmatch(r'[0-9a-f]{1,16}', identity or ''):
            args = ['announcement','show',identity]
        elif operation in allowed:
            args = allowed[operation]
        else:
            raise CampusError('invalid_operation','不支持的教学网操作。')
        if otp:
            if not re.fullmatch(r'[0-9]{6}',otp):
                raise CampusError('invalid_code','OTP 应为六位数字。')
            args = [args[0],'--otp-code',otp,*args[1:]]
        status = self.status()
        if status['state'] != 'configured':
            raise CampusError(status['state'],status['message'])
        cmd = [self.executable(), '--config',str(local_path(self.config.get('config_file','private/pku3b.toml'))),
               '--cache-dir',str(local_path(self.config.get('cache_dir','private/pku3b-cache'))), *args]
        try:
            result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                                    timeout=min(120,max(5,int(self.config.get('timeout_seconds',60)))),
                                    env={**os.environ,'NO_COLOR':'1','CLICOLOR':'0','RUST_LOG':'off'})
        except subprocess.TimeoutExpired:
            raise CampusError('timeout','教学网读取超时，旧数据已保留；若需 OTP，请先在终端登录。') from None
        except OSError:
            raise CampusError('client_failed','无法启动 pku3b，请核对可执行文件。') from None
        if result.returncode:
            raise CampusError('login_or_network','pku3b 读取失败，请在终端检查登录、OTP 和校内网络；旧数据已保留。')
        return result.stdout.decode('utf-8',errors='replace')

    def fetch(self, kind, otp=''):
        output = self.run(kind,otp=otp)
        return parse_timetable(output) if kind == 'course' else parse_list(output,kind)

    def detail(self, doc):
        text = ANSI.sub('', self.run('announcement_detail',doc['sourceId'])).strip()
        if f"ID: {doc['sourceId']}" not in text:
            raise CampusError('unsupported_output','公告详情格式不匹配。')
        return {**doc,'text':text,'detailLoaded':True,'fetchedAt':now()}
