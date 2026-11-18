"""Manual official-site login in an isolated browser; session export stays local."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from .config import ROOT, CampusError, local_path, load_config

TARGETS = {
    'treehole':'https://treehole.pku.edu.cn/web/',
    'blackboard':'https://course.pku.edu.cn/',
    'portal':'https://portal.pku.edu.cn/publicQuery/',
}
ALLOWED_COOKIE_DOMAINS = {'treehole.pku.edu.cn','course.pku.edu.cn','portal.pku.edu.cn','iaaa.pku.edu.cn','pku.edu.cn'}


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def filter_cookies(cookies,source):
    domains = {'treehole.pku.edu.cn','pku.edu.cn'} if source == 'treehole' else {'course.pku.edu.cn','portal.pku.edu.cn','iaaa.pku.edu.cn','pku.edu.cn'}
    return [c for c in cookies if c.get('domain','').lstrip('.') in domains and (c.get('expires',-1) <= 0 or c['expires'] > time.time())]


def rust_cookies(cookies):
    result=[]
    for cookie in cookies:
        domain=cookie['domain']
        if domain.lstrip('.') not in ALLOWED_COOKIE_DOMAINS:
            continue
        # Preserve host-only/suffix scope and actual expiry, including HttpOnly.
        raw=f"{cookie['name']}={cookie['value']}; Path={cookie.get('path','/')}"
        if domain.startswith('.'):
            raw += '; Domain=' + domain
        if cookie.get('secure'):
            raw += '; Secure'
        if cookie.get('httpOnly'):
            raw += '; HttpOnly'
        expiry=cookie.get('expires',-1)
        result.append({'raw_cookie':raw,'path':[cookie.get('path','/'),True],
                       'domain':{'Suffix' if domain.startswith('.') else 'HostOnly':domain.lstrip('.')},
                       'expires':{'AtUtc':datetime.fromtimestamp(expiry,timezone.utc).isoformat().replace('+00:00','Z')} if expiry > 0 else 'SessionEnd'})
    return result


def save_session(source,cookies,token='',config=None,device_uuid='',user_agent=''):
    config=load_config() if config is None else config
    cookies=filter_cookies(cookies,source)
    if source == 'treehole':
        if not token:
            raise CampusError('missing_token','还未捕获到有效树洞登录会话，请先完成登录验证并打开树洞首页。')
        path=local_path(config.get('treehole',{}).get('session_file','private/treehole-session.json'))
        write_json(path,{'token':token,'cookies':cookies,'uuid':device_uuid,'userAgent':user_agent,'loginMethod':'browser'})
    else:
        cfg=config.get('blackboard',{})
        cache=local_path(cfg.get('cache_dir','private/pku3b-cache'))
        target=cache / 'ua.json'
        converted=rust_cookies(cookies)
        # Preserve the other campus system's previously exported cookies.
        try:
            previous=json.loads(target.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            previous=[]
        keys={(json.dumps(c['domain'],sort_keys=True),c['path'][0],c['raw_cookie'].split('=',1)[0]) for c in converted}
        retained=[c for c in previous if (json.dumps(c.get('domain',{}),sort_keys=True),c.get('path',['/'])[0],c.get('raw_cookie','').split('=',1)[0]) not in keys]
        write_json(target,retained+converted)
        write_json(ROOT / f'private/{source}-browser-session.json',{'cookies':cookies,'loginMethod':'browser','savedAt':datetime.now(timezone.utc).isoformat()})


class BrowserLogins:
    def __init__(self):
        self.lock=threading.Lock()
        self.job=None
        self.process=None

    def status(self):
        if not self.job:
            return {'state':'idle'}
        path=ROOT / 'private/browser-login-jobs' / (self.job+'.json')
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            data={'state':'starting'}
        if self.process and self.process.poll() is not None and data.get('state') not in ('ready','failed','cancelled'):
            data={'state':'failed','message':'登录窗口已关闭或无法启动，请重试。'}
        # No cookie/token/profile contents are returned to HTTP clients.
        return {key:data[key] for key in ('state','source','message') if key in data}

    def start(self,source):
        if source not in TARGETS:
            raise CampusError('invalid_source','仅支持教学网、课表门户和树洞登录。')
        with self.lock:
            if self.process and self.process.poll() is None:
                raise CampusError('busy','已有登录窗口，请先完成或关闭。')
            self.job=secrets.token_hex(16)
            path=ROOT / 'private/browser-login-jobs' / (self.job+'.json')
            write_json(path,{'state':'starting','source':source,'message':'正在打开独立 Chrome 登录窗口…'})
            flags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            self.process=subprocess.Popen([sys.executable,str(ROOT/'scripts/browser_login.py'),'--source',source,'--job',self.job],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,cwd=ROOT,creationflags=flags)
            return {'state':'starting','source':source,'message':'请在弹出的官方页面自行登录，再返回工作台点击“完成登录”。'}

    def finish(self):
        if not self.job or not self.process or self.process.poll() is not None:
            raise CampusError('not_running','没有正在进行的浏览器登录。')
        path=ROOT / 'private/browser-login-jobs' / (self.job+'.finish')
        path.write_text('verify',encoding='ascii')
        return {'state':'verifying','message':'正在验证官方站点登录状态…'}


BROWSER_LOGINS=BrowserLogins()


def verify_treehole_response(status,data):
    if status==200 and isinstance(data,dict) and data.get('code')==20000 and isinstance(data.get('data'),dict) and isinstance(data['data'].get('list'),list):
        return
    code=data.get('code') if isinstance(data,dict) else None
    if code in (40002,40099,40088,40008,40009,40010):
        raise CampusError('needs_verification','官方检索接口仍要求验证，请在当前 Chrome 页面完成验证后重试。')
    if status in (401,403):
        raise CampusError('needs_login','当前会话无法访问检索接口，请刷新 Chrome 中的树洞首页后重试。')
    raise CampusError('verification_failed','检索接口未返回预期结果；这不等于二次验证未完成，请稍后重试。')


def run_browser_login(source,job):
    if source not in TARGETS or not re.fullmatch('[a-f0-9]{32}',job):
        return
    status_path=ROOT / 'private/browser-login-jobs' / (job+'.json')
    finish_path=status_path.with_suffix('.finish')
    cancel_path=status_path.with_suffix('.cancel')
    def report(state,message):
        write_json(status_path,{'state':state,'source':source,'message':message})
    sys.path.insert(0,str(ROOT / '.runtime'))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        report('failed','缺少 Playwright，请安装 requirements-browser.txt 后重试。')
        return
    try:
        with sync_playwright() as playwright:
            profile=ROOT / 'private/browser-profiles' / source
            context=playwright.chromium.launch_persistent_context(str(profile),channel='chrome',headless=False)
            browser=context
            page=context.pages[0] if context.pages else context.new_page()
            captured={'token':'','uuid':'','userAgent':''}
            def observe(request):
                from urllib.parse import urlparse
                parsed=urlparse(request.url)
                if source=='treehole' and parsed.scheme=='https' and parsed.hostname=='treehole.pku.edu.cn' and parsed.path.startswith(('/api/','/chapi/')):
                    auth=request.header_value('authorization') or ''
                    if auth.lower().startswith('bearer '):
                        captured['token']=auth[7:]
                    device_uuid=request.header_value('uuid')
                    if device_uuid:
                        captured['uuid']=device_uuid
                    agent=request.header_value('user-agent')
                    if agent:
                        captured['userAgent']=agent
            context.on('request',observe)
            try:
                page.goto(TARGETS[source],wait_until='domcontentloaded',timeout=30000)
            except Exception:
                pass
            report('waiting','请在官方页面完成登录及二次验证，再回工作台点击“完成登录”。无需复制 Cookie。')
            deadline=time.monotonic()+600
            while time.monotonic() < deadline:
                if cancel_path.exists():
                    report('cancelled','已关闭本项目的登录窗口，未更改现有会话。')
                    browser.close()
                    return
                if not context.pages:
                    report('cancelled','登录窗口已关闭，未更改现有会话。')
                    return
                if finish_path.exists():
                    finish_path.unlink()
                    try:
                        token=captured['token']
                        device_uuid=captured['uuid']
                        user_agent=captured['userAgent']
                        if source=='treehole':
                            # The current cookie wins over a token observed before MFA.
                            token=next((c['value'] for c in context.cookies() if c['name']=='pku_token' and c['domain'].lstrip('.') in ('treehole.pku.edu.cn','pku.edu.cn')),token)
                            for candidate in context.pages:
                                from urllib.parse import urlparse
                                if urlparse(candidate.url).hostname=='treehole.pku.edu.cn':
                                    device_uuid=candidate.evaluate("localStorage.getItem('pku-uuid') || ''") or device_uuid
                                    user_agent=candidate.evaluate('navigator.userAgent')
                                    break
                            if not token:
                                raise CampusError('missing_token','请先进入已登录的树洞首页，让页面完成数据加载，再点击完成。')
                            if not device_uuid:
                                raise CampusError('missing_device','尚未取到网页设备标识，请先刷新树洞首页并等待数据加载。')
                            headers={'Authorization':'Bearer '+token,'Uuid':device_uuid,'User-Agent':user_agent,'Referer':TARGETS['treehole']}
                            response=context.request.get('https://treehole.pku.edu.cn/chapi/api/v3/hole/list_comments',params={'keyword':'课程','page':1,'limit':1,'comment_limit':0},headers=headers,timeout=15000,max_redirects=0)
                            verify_treehole_response(response.status,response.json())
                        elif source=='blackboard':
                            response=context.request.get('https://course.pku.edu.cn/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1',timeout=15000,max_redirects=0)
                            text=response.text()
                            if response.status != 200 or not re.search(r'course_id=|courseMemberships|courseListing|action=logout',text):
                                raise CampusError('needs_login','未确认已进入教学网个人首页，请完成 IAAA 登录。')
                        else:
                            response=context.request.get('https://portal.pku.edu.cn/publicQuery/ctrl/topic/myCourseTable/getXndXqList.do',timeout=15000,max_redirects=0)
                            data=response.json()
                            if response.status != 200 or not isinstance(data,dict) or not isinstance(data.get('nowXnxq'),dict) or not data['nowXnxq'].get('xndxq'):
                                raise CampusError('needs_login','尚未读到个人课表学期，请先登录门户的课表查询页。')
                        save_session(source,context.cookies(),token,device_uuid=device_uuid,user_agent=user_agent)
                        report('ready','登录已验证，会话已保存到本机。可以关闭登录窗口并返回检索。')
                        browser.close()
                        return
                    except CampusError as exc:
                        report('waiting',str(exc))
                    except Exception:
                        report('waiting','尚未验证登录成功，请确认官方页面正常加载后重试。')
                page.wait_for_timeout(500)
            report('cancelled','登录等待超时，未覆盖现有会话。')
            browser.close()
    except Exception:
        report('failed','无法启动或连接独立 Chrome 登录窗口；请确认 Chrome 已安装，或重新尝试。')
