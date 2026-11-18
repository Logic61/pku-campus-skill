"""Bounded treehole retrieval. Credentials are only sent to PKU HTTPS hosts."""
import json
import threading
import time
import uuid
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from .config import CampusError, local_path
from .store import now

TREE = 'https://treehole.pku.edu.cn'
RATE_LOCK = threading.Lock()
LAST_REQUEST = 0.0


def timestamp(value):
    try:
        return datetime.fromtimestamp(float(value),timezone.utc).isoformat()
    except (TypeError,ValueError,OverflowError,OSError):
        return None


def normalize_post(post):
    identity = str(post.get('pid',''))
    if not identity.isdigit():
        raise CampusError('upstream_schema','树洞返回缺少有效帖号。')
    text = str(post.get('text') or '')
    comments = post.get('comment_list') or post.get('comments') or []
    comments = [{'id':str(c.get('cid','')), 'text':str(c.get('text') or ''),
                 'publishedAt':timestamp(c.get('timestamp'))} for c in comments[:30] if isinstance(c,dict)]
    return {'id':f'treehole:post:{identity}', 'sourceId':identity, 'source':'treehole', 'kind':'post',
            'title':text[:100] or f'树洞 #{identity}', 'text':text,
            'comments':comments, 'commentTotal':post.get('comment_total',post.get('reply',0)),
            'commentsComplete':False, 'url':f'{TREE}/web/#/hole/{identity}',
            'publishedAt':timestamp(post.get('timestamp')), 'fetchedAt':now(),
            'visibility':'private', 'contentTrust':'untrusted_user_content'}


class Treehole:
    def __init__(self, config):
        self.config = config
        self.token = config.get('token','').strip()
        self.session_path = local_path(config.get('session_file','private/treehole-session.json'))
        self.session = None
        self.device_uuid = ''

    def status(self):
        if not self.config.get('enabled',False):
            return {'state':'disabled','message':'树洞连接器未启用。'}
        if self.token or self.session_path.is_file():
            return {'state':'configured','message':'已有会话配置，实际有效性将在查询时验证。'}
        if self.config.get('username') and self.config.get('password'):
            return {'state':'needs_login','message':'请运行 python manage.py login-treehole 完成登录验证。'}
        return {'state':'needs_credentials','message':'请在 private/config.toml 填入树洞账号密码或现有 Bearer token。'}

    def _session(self):
        if self.session is not None:
            return self.session
        try:
            import requests
        except ImportError:
            raise CampusError('missing_dependency','请先 python -m pip install -r requirements.txt。') from None
        self.session = requests.Session()
        self.session.headers.update({'User-Agent':'Mozilla/5.0 AWE-PKU/0.2', 'Referer':f'{TREE}/web/'})
        if self.session_path.is_file():
            try:
                saved = json.loads(self.session_path.read_text(encoding='utf-8'))
                self.device_uuid = str(saved.get('uuid',''))
                if saved.get('userAgent'):
                    self.session.headers['User-Agent'] = saved['userAgent']
                self.token = saved.get('token','') if saved.get('loginMethod') == 'browser' else self.token or saved.get('token','')
                for cookie in saved.get('cookies',[]):
                    if cookie.get('domain','').lstrip('.') not in ('treehole.pku.edu.cn','iaaa.pku.edu.cn','pku.edu.cn'):
                        continue
                    self.session.cookies.set(cookie['name'],cookie['value'],domain=cookie['domain'],path=cookie.get('path','/'),secure=True)
            except (OSError,ValueError,KeyError,TypeError):
                raise CampusError('invalid_session','树洞会话文件损坏，请重新登录。') from None
        if self.token:
            self.session.headers['Authorization'] = f'Bearer {self.token}'
        self.device_uuid = self.device_uuid or 'Web_PKUHOLE_2.0.0_WEB_UUID_' + str(uuid.uuid4())
        self.session.headers['Uuid'] = self.device_uuid
        return self.session

    def _request(self, method, url, **kwargs):
        global LAST_REQUEST
        session = self._session()
        host = urlparse(url).hostname
        if urlparse(url).scheme != 'https' or host not in ('treehole.pku.edu.cn','iaaa.pku.edu.cn'):
            raise CampusError('invalid_destination','拒绝向非授权目标发送登录信息。')
        # Separate OAuth session: never send the treehole Bearer token to IAAA.
        headers = dict(kwargs.pop('headers',{}))
        if host == 'iaaa.pku.edu.cn':
            headers['Authorization'] = None
        with RATE_LOCK:
            time.sleep(max(0,1.0-(time.monotonic()-LAST_REQUEST)))
            LAST_REQUEST = time.monotonic()
        try:
            response = session.request(method,url,headers=headers,timeout=min(60,max(5,int(self.config.get('timeout_seconds',20)))),allow_redirects=False,**kwargs)
        except Exception:
            raise CampusError('network_error','无法连接树洞或认证服务，请检查校园网、代理与证书。') from None
        if response.status_code in (401,403):
            raise CampusError('needs_login','树洞会话失效或需要额外验证，请在本机终端重新登录。')
        if response.status_code == 429:
            raise CampusError('rate_limited','树洞请求受限，请稍后再试。')
        if response.status_code >= 400:
            raise CampusError('upstream_error','树洞服务返回错误，未更新本机缓存。')
        return response

    def _json(self,response):
        try:
            data = response.json()
            if not isinstance(data,dict):
                raise ValueError()
            return data
        except ValueError:
            raise CampusError('upstream_schema','树洞返回的不是预期 JSON，可能需要重新登录。') from None

    def _save(self):
        self.session_path.parent.mkdir(parents=True,exist_ok=True)
        cookies = [{'name':c.name,'value':c.value,'domain':c.domain,'path':c.path} for c in self._session().cookies]
        temp = self.session_path.with_suffix('.tmp')
        temp.write_text(json.dumps({'token':self.token,'cookies':cookies,'uuid':self.device_uuid,'userAgent':self._session().headers.get('User-Agent','')}),encoding='utf-8')
        temp.replace(self.session_path)

    def login(self, username, password, otp=''):
        if not self.config.get('enabled',False):
            raise CampusError('disabled','树洞连接器未启用。')
        if not username or not password:
            raise CampusError('needs_credentials','请先填写树洞账号密码。')
        data = self._json(self._request('POST','https://iaaa.pku.edu.cn/iaaa/oauthlogin.do',data={
            'appid':'PKU Helper','userName':username,'password':password,'randCode':'','smsCode':'','otpCode':otp,
            'redirUrl':f'{TREE}/cas_iaaa_login?uuid=fc71db5799cf&plat=web'}))
        if data.get('success') not in (True,'true') or not data.get('token'):
            raise CampusError('login_failed','IAAA 登录失败，请核对账号密码或 OTP；服务不会输出上游响应中的敏感字段。')
        response = self._request('GET',f'{TREE}/cas_iaaa_login',params={
            'uuid':'fc71db5799cf','plat':'web','token':data['token'],'_rand':str(time.time())})
        # Follow only same-host HTTPS redirects, with an explicit small bound.
        from urllib.parse import urljoin
        for _ in range(5):
            location = response.headers.get('Location','')
            candidate = urljoin(response.url,location) if location else response.url
            parsed = urlparse(candidate)
            if parsed.scheme != 'https' or parsed.hostname != 'treehole.pku.edu.cn':
                raise CampusError('unsafe_redirect','认证跳转不是树洞 HTTPS 地址，已停止。')
            fragment_query = parsed.fragment.split('?',1)[-1].lstrip('/?')
            token = (parse_qs(parsed.query).get('token') or parse_qs(fragment_query).get('token')) if parsed.path != '/cas_iaaa_login' else None
            if token:
                self.token = token[0]
                self._session().headers['Authorization'] = f'Bearer {self.token}'
                break
            if not (300 <= response.status_code < 400 and location):
                break
            response = self._request('GET',candidate)
        if not self.token:
            raise CampusError('login_failed','认证返回未包含树洞 token；可改用已有 Bearer token 配置。')
        return self.check_login()

    def check_login(self):
        data = self._json(self._request('GET',f'{TREE}/api/mail/un_read'))
        if data.get('success') in (True,'true'):
            self._save()
            return {'state':'ready','message':'树洞登录验证成功。'}
        message = str(data.get('message',''))
        if '令牌' in message:
            return {'state':'needs_mobile_token','message':'需要六位手机令牌验证。'}
        if '短信' in message:
            return {'state':'needs_sms','message':'需要短信验证；当前不自动发送短信，可在官方网页完成后配置 Bearer token。'}
        raise CampusError('needs_login','树洞登录尚未通过，请在官方网页检查验证要求。')

    def verify_mobile(self,code):
        if not str(code).isdigit() or len(str(code)) != 6:
            raise CampusError('invalid_code','手机令牌应为六位数字。')
        data = self._json(self._request('POST',f'{TREE}/api/login_iaaa_check_token',data={'code':code}))
        new_token = data.get('token') or (data.get('data') or {}).get('token')
        if new_token:
            self.token = new_token
            self._session().headers['Authorization'] = f'Bearer {self.token}'
        return self.check_login()

    def require_session(self):
        status = self.status()
        if status['state'] != 'configured':
            raise CampusError(status['state'],status['message'])

    def search(self,query,limit=10,page=1):
        self.require_session()
        data = self._json(self._request('GET',f'{TREE}/chapi/api/v3/hole/list_comments',params={
            'keyword':query,'page':page,'limit':limit,'comment_limit':5}))
        if data.get('code') != 20000:
            raise CampusError('needs_login' if data.get('code') in (401,403) else 'upstream_error','树洞检索未成功，请验证会话或稍后重试。')
        payload = data.get('data')
        if not isinstance(payload,dict) or not isinstance(payload.get('list'),list):
            raise CampusError('upstream_schema','树洞检索响应结构已变化。')
        return [normalize_post(post) for post in payload['list'][:limit]], payload.get('total')

    def detail(self,identity,page=1,limit=20):
        self.require_session()
        if not re_pid(identity):
            raise CampusError('invalid_id','无效树洞帖号。')
        data = self._json(self._request('GET',f'{TREE}/api/pku/{identity}'))
        if data.get('success') not in (True,'true') or not isinstance(data.get('data'),dict):
            raise CampusError('unavailable','帖子不可用、已删除或会话失效。')
        post = data['data']
        if str(post.get('pid','')) != str(identity):
            raise CampusError('upstream_schema','详情响应的帖号不匹配。')
        comment_data = self._json(self._request('GET',f'{TREE}/api/pku_comment_v3/{identity}',params={'page':page,'limit':limit,'sort':'asc'}))
        comments = comment_data.get('data')
        # The live API uses an empty object for a post with explicitly zero replies.
        if comment_data.get('success') in (True,'true') and comments == {} and post.get('reply') in (0,'0'):
            comments = {'data':[], 'total':0}
        if comment_data.get('success') not in (True,'true') or not isinstance(comments,dict) or not isinstance(comments.get('data'),list):
            raise CampusError('upstream_schema','评论不可用或结构已变化；未把评论失败当成零条评论。')
        doc = normalize_post({**post,'comment_list':comments['data']})
        doc.update({'commentPage':page,'commentPageSize':limit,'commentTotal':comments.get('total',doc['commentTotal']),
                    'commentsComplete':page == 1 and isinstance(comments.get('total'),int) and comments['total'] <= len(doc['comments'])})
        return doc

    def scan_high_comments(self,query='',min_comments=100,start_page=1,pages=15,page_size=50):
        """Bounded list scan; never mistakes a partial sample for a global ranking."""
        self.require_session()
        seen,matched=set(),{}
        scanned_pages=0
        warnings=[]
        stop_reason='page_budget'
        for page in range(start_page,start_page+pages):
            params={'page':page,'limit':page_size,'comment_limit':0}
            if query.strip():
                params['keyword']=query.strip()
            try:
                data=self._json(self._request('GET',f'{TREE}/chapi/api/v3/hole/list_comments',params=params))
                payload=data.get('data')
                if data.get('code')!=20000 or not isinstance(payload,dict) or not isinstance(payload.get('list'),list):
                    raise CampusError('upstream_error','列表读取未成功，扫描已停止，已读结果仍保留。')
                rows=payload['list']
                scanned_pages+=1
                if not rows:
                    stop_reason='empty_page'
                    break
                new_count=0
                for row in rows:
                    identity=str(row.get('pid',''))
                    if not re_pid(identity) or identity in seen:
                        continue
                    seen.add(identity);new_count+=1
                    count=row.get('comment_total',row.get('reply'))
                    if isinstance(count,bool):
                        continue
                    try:
                        count=int(count)
                    except (ValueError,TypeError):
                        continue
                    if count>min_comments:
                        doc=normalize_post(row)
                        doc['commentTotal']=count
                        matched[identity]=doc
                if new_count==0:
                    stop_reason='repeated_page'
                    warnings.append({'code':'repeated_page','message':'来源返回重复页，停止扫描，避免重复请求。'})
                    break
                # Do not use page*requested_limit >= reported total: the server
                # may cap page size, and its total is not a reliable end marker.
            except CampusError as exc:
                warnings.append({'page':page,**exc.as_dict()})
                stop_reason='error'
                break
        items=sorted(matched.values(),key=lambda d:(d['commentTotal'],d['sourceId']),reverse=True)
        return {'query':query,'minCommentsExclusive':min_comments,'startPage':start_page,
                'requestedPages':pages,'scannedPages':scanned_pages,'scannedUniquePosts':len(seen),
                'matchedCount':len(items),'items':items,'warnings':warnings,'stopReason':stop_reason,
                'nextPage':start_page+scanned_pages if stop_reason=='page_budget' else None,
                'coverage':'仅对所读取列表页按总评论数筛选和排序，不是全站历史排名。'}


def re_pid(value):
    return isinstance(value,str) and value.isascii() and value.isdigit() and 0 < len(value) <= 12
