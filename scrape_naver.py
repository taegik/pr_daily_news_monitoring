#!/usr/bin/env python3
"""상상인그룹 PR팀 데일리 뉴스 모니터링 - 수집/아카이브 스크립트

모드 (환경변수 RUN_MODE)
  scrape   : 네이버 검색 API(우선) + 구글 뉴스 RSS(보조)로 계열사별 후보 기사 수집 -> scraped_pool.json
  archive  : published_data.json 의 발행분을 archive/ 에 날짜별로 저장, 대표 이미지 보강, 90일 초과분 정리

필요한 환경변수(scrape): NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
"""
import os
import re
import sys
import json
import time
import glob
import html
import base64
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))
POOL_FILE = 'scraped_pool.json'
PUBLISHED_FILE = 'published_data.json'
KEYWORD_FILE = 'keywords.json'
ARCHIVE_DIR = 'archive'
STATS_FILE = os.path.join(ARCHIVE_DIR, 'stats.json')
INDEX_FILE = os.path.join(ARCHIVE_DIR, 'index.json')
SEARCH_FILE = os.path.join(ARCHIVE_DIR, 'search.json')
RETENTION_DAYS = 90
POOL_CAP_PER_AFFILIATE = 300
AFFILIATE_ORDER = ['sangsangin', 'mitech', 'synergy', 'medica', 'neurobiogen']

CRON_MORNING_SANGSANGIN = '35 22 * * 0-4'   # KST 07:35 (상상인 8시 발행)
CRON_MORNING_AFFILIATES = '35 23 * * 0-4'   # KST 08:35 (계열사 9시 발행)

# 도메인 -> 언론사명 (구체적인 도메인이 먼저 매칭되도록 긴 것부터 검사)
DOMAIN_PRESS_MAP = {
    'biz.chosun.com': '조선비즈', 'investchosun.com': '인베스트조선', 'chosun.com': '조선일보',
    'hankyung.com': '한국경제', 'mk.co.kr': '매일경제', 'sedaily.com': '서울경제',
    'fnnews.com': '파이낸셜뉴스', 'edaily.co.kr': '이데일리', 'mt.co.kr': '머니투데이',
    'asiae.co.kr': '아시아경제', 'heraldcorp.com': '헤럴드경제', 'dt.co.kr': '디지털타임스',
    'etnews.com': '전자신문', 'inews24.com': '아이뉴스24', 'joongang.co.kr': '중앙일보',
    'donga.com': '동아일보', 'yna.co.kr': '연합뉴스', 'newsis.com': '뉴시스', 'news1.kr': '뉴스1',
    'einfomax.co.kr': '연합인포맥스', 'hani.co.kr': '한겨레', 'khan.co.kr': '경향신문',
    'hankookilbo.com': '한국일보', 'seoul.co.kr': '서울신문', 'kmib.co.kr': '국민일보',
    'segye.com': '세계일보', 'munhwa.com': '문화일보', 'ohmynews.com': '오마이뉴스',
    'ytn.co.kr': 'YTN', 'kbs.co.kr': 'KBS', 'imbc.com': 'MBC', 'sbs.co.kr': 'SBS',
    'jtbc.co.kr': 'JTBC', 'mbn.co.kr': 'MBN', 'tvchosun.com': 'TV조선', 'ichannela.com': '채널A',
    'wowtv.co.kr': '한국경제TV', 'mtn.co.kr': 'MTN',
    'dailypharm.com': '데일리팜', 'medipana.com': '메디파나뉴스', 'newsmp.com': '의약뉴스',
    'bosa.co.kr': '의학신문', 'kpanews.co.kr': '약사공론', 'yakup.com': '약업신문',
    'hitnews.co.kr': '히트뉴스', 'biospectator.com': '바이오스펙테이터', 'docdocdoc.co.kr': '청년의사',
    'dailymedi.com': '데일리메디', 'medicaltimes.com': '메디컬타임즈', 'rapportian.com': '라포르시안',
    'bokuennews.com': '보건뉴스', 'skyedaily.com': '스카이데일리', 'ceoscoredaily.com': 'CEO스코어데일리',
    'sisajournal-e.com': '시사저널e', 'asiatime.co.kr': '아시아타임즈', 'tf.co.kr': '더팩트',
    'm-i.kr': '매일일보', 'thebell.co.kr': '더벨', 'zdnet.co.kr': '지디넷코리아', 'bloter.net': '블로터',
    'newsway.co.kr': '뉴스웨이', 'newspim.com': '뉴스핌', 'ajunews.com': '아주경제',
    'businesspost.co.kr': '비즈니스포스트', 'etoday.co.kr': '이투데이', 'asiatoday.co.kr': '아시아투데이',
    'viva100.com': '브릿지경제', 'metroseoul.co.kr': '메트로신문', 'bizwatch.co.kr': '비즈워치',
    'fntimes.com': '한국금융', 'ebn.co.kr': 'EBN', 'dnews.co.kr': '대한경제', 'kukinews.com': '쿠키뉴스',
    'medigatenews.com': '메디게이트뉴스', 'pharmnews.com': '팜뉴스', 'hellodd.com': '헬로티',
}

PRESS_TIER_1 = [
    "연합뉴스", "뉴시스", "뉴스1", "연합인포맥스",
    "한국경제", "매일경제", "서울경제", "파이낸셜뉴스", "이데일리", "머니투데이", "아시아경제", "헤럴드경제", "조선비즈",
    "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문",
    "KBS", "MBC", "SBS", "YTN", "JTBC", "MBN", "TV조선", "채널A", "한국경제TV", "MTN"
]

PRESS_TIER_2 = [
    "데일리팜", "메디파나뉴스", "의약뉴스", "의학신문", "약사공론", "약업신문",
    "히트뉴스", "바이오스펙테이터", "청년의사", "데일리메디", "메디컬타임즈", "라포르시안", "보건뉴스",
    "전자신문", "디지털타임스", "아이뉴스24", "지디넷코리아", "블로터", "더벨", "인베스트조선",
    "시사저널e", "비즈니스포스트", "CEO스코어데일리", "이투데이", "아시아투데이", "브릿지경제", "메트로신문"
]

UA_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"
}


def log(msg):
    print(msg, flush=True)


def warn(msg):
    # GitHub Actions 워크플로 경고 어노테이션
    print(f"::warning::{msg}", flush=True)


# ---------------------------------------------------------------------------
# 공통 유틸 (기존 코드 재사용)
# ---------------------------------------------------------------------------
class MetaTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'meta':
            return
        attr_dict = {k.lower(): (v or '') for k, v in attrs if k}
        key = (attr_dict.get('property') or attr_dict.get('name') or '').strip().lower()
        content = attr_dict.get('content', '').strip()
        if key and content and key not in self.meta:
            self.meta[key] = content


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_html(raw):
    text = re.sub(r'<[^>]+>', '', raw or '')
    return html.unescape(text).strip()


def normalize_title(title):
    t = re.sub(r'\[[^\]]*\]', '', title or '')
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', t).lower()


def search_original_url_by_title(title, press=""):
    """구글 뉴스 암호화 링크 해석이 막혔을 때 기사 제목으로 다음(Daum) 뉴스 검색에서 원본 URL 역추적"""
    clean_t = re.sub(r'\[[^\]]*\]', ' ', title or '')
    clean_t = re.sub(r'[^\w\s가-힣]', ' ', clean_t)
    clean_t = re.sub(r'\s+', ' ', clean_t).strip()
    if len(clean_t) < 6:
        return ""

    query = f"{press} {clean_t}".strip() if press and press != '주요언론' else clean_t
    try:
        q_enc = urllib.parse.quote(query)
        daum_url = f"https://search.daum.net/search?w=news&q={q_enc}&sort=accuracy"
        req = urllib.request.Request(daum_url, headers=UA_HEADER)
        with urllib.request.urlopen(req, timeout=8) as resp:
            d_html = resp.read().decode('utf-8', errors='ignore')

        # 다음 뉴스 검색 결과의 외부 언론사 원문 링크 추출
        links = re.findall(r'href="(https?://[^"]+)"', d_html)
        for u in links:
            u_clean = html.unescape(u)
            host = urllib.parse.urlparse(u_clean).netloc.lower()
            if not host:
                continue
            if any(skip in host for skip in ('daum.net', 'kakao.com', 'google.com', 'naver.com', 'youtube.com', 'facebook.com', 'twitter.com', 'x.com')):
                continue
            if len(urllib.parse.urlparse(u_clean).path) > 5:
                return u_clean
    except Exception:
        pass
    return ""


def resolve_google_news_url(gnews_url, title="", press=""):
    if 'news.google.com' not in gnews_url:
        return gnews_url

    parsed = urllib.parse.urlparse(gnews_url)
    path_parts = parsed.path.split('/')
    article_token = path_parts[-1] if path_parts else ''

    # 방법 1: 구형 Base64 토큰 직접 디코딩
    try:
        b64_str = article_token
        padding = 4 - (len(b64_str) % 4)
        if padding != 4:
            b64_str += '=' * padding
        decoded_bytes = base64.urlsafe_b64decode(b64_str)
        m_url = re.search(rb'https?://[A-Za-z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+', decoded_bytes)
        if m_url:
            candidate = m_url.group(0).decode('utf-8', errors='ignore')
            if 'news.google.com' not in candidate and 'gstatic.com' not in candidate:
                return candidate
    except Exception:
        pass

    # 방법 2: 신형 Google News 토큰 -> batchexecute API 디코딩
    try:
        page_url = f"https://news.google.com/rss/articles/{article_token}"
        req = urllib.request.Request(page_url, headers=UA_HEADER)
        with urllib.request.urlopen(req, timeout=8) as resp:
            if 'news.google.com' not in resp.geturl():
                return resp.geturl()
            html_str = resp.read().decode('utf-8', errors='ignore')

        m_sig = re.search(r'data-n-a-sg="([^"]+)"', html_str)
        m_ts = re.search(r'data-n-a-ts="([^"]+)"', html_str)
        if m_sig and m_ts:
            sig = m_sig.group(1)
            ts = m_ts.group(1)
            inner_payload = json.dumps([
                "garturlreq",
                [["X", "X", ["X", "X"], None, None, 1, 1, "KR:ko", None, 1, None, None, None, None, None, 0, 1],
                 "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                article_token,
                int(ts),
                sig
            ])
            f_req = urllib.parse.quote(json.dumps([[["Fbv4je", inner_payload, None, "generic"]]]))
            batch_req = urllib.request.Request(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                data=f"f.req={f_req}".encode('utf-8'),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "User-Agent": UA_HEADER["User-Agent"]
                }
            )
            with urllib.request.urlopen(batch_req, timeout=8) as b_resp:
                b_text = b_resp.read().decode('utf-8', errors='ignore')
                m_real = re.search(r'garturlres","(https?://[^"\\]+)', b_text)
                if m_real:
                    decoded = m_real.group(1).replace('\\u003d', '=').replace('\\u0026', '&')
                    if 'news.google.com' not in decoded:
                        return decoded
    except Exception:
        pass

    # 방법 3: 구글 디코딩 차단 시 기사 제목+언론사로 다음 뉴스에서 원본 URL 역추적
    if title:
        traced = search_original_url_by_title(title, press)
        if traced:
            return traced

    return gnews_url


# ---------------------------------------------------------------------------
# 언론사/키워드/랭킹
# ---------------------------------------------------------------------------
def extract_press(url):
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        for domain in sorted(DOMAIN_PRESS_MAP, key=len, reverse=True):
            if host == domain or host.endswith('.' + domain) or host.endswith(domain):
                return DOMAIN_PRESS_MAP[domain]
        parts = host.replace('www.', '').split('.')
        # co.kr / or.kr 같은 2단계 TLD 처리
        if len(parts) >= 3 and parts[-2] in ('co', 'or', 'go', 'ne', 'com'):
            return parts[-3]
        return parts[-2] if len(parts) >= 2 else (parts[0] if parts else '주요언론')
    except Exception:
        return '주요언론'


def press_tier(press):
    p = (press or '').strip()
    if any(t in p or p in t for t in PRESS_TIER_1 if p):
        return 1
    if any(t in p or p in t for t in PRESS_TIER_2 if p):
        return 2
    return 3


def normalize_keywords(entry):
    """키워드 항목을 {'own': [], 'comp': [], 'ind': []} 형태로 정규화 (구버전 평면 리스트 호환)"""
    out = {'own': [], 'comp': [], 'ind': []}
    if isinstance(entry, dict):
        for g in out:
            out[g] = [k.strip() for k in entry.get(g, []) if k and k.strip()]
    elif isinstance(entry, list):
        flat = [k.strip() for k in entry if k and k.strip()]
        if flat:
            out['own'] = flat[:1]
            out['ind'] = flat[1:]
    for g in out:
        out[g] = list(dict.fromkeys(out[g]))
    return out


def load_keywords(pool_data):
    raw = load_json(KEYWORD_FILE, None)
    if not raw:
        raw = (pool_data or {}).get('keywords') or {}
    result = {}
    for aff in AFFILIATE_ORDER:
        if aff in raw:
            result[aff] = normalize_keywords(raw[aff])
    return result


def compact(s):
    return re.sub(r'\s+', '', (s or '').lower())


def kw_in_text(kw, text_compact):
    k = compact(kw)
    if not k:
        return False
    return k in text_compact


def classify(title, desc, query_kw, kw_groups):
    """자사 키워드가 제목에 있으면 own, 경쟁사 키워드가 제목에 있으면 comp, 아니면 검색 키워드의 그룹"""
    t = compact(title)
    for kw in kw_groups['own']:
        if kw_in_text(kw, t):
            return 'own'
    for kw in kw_groups['comp']:
        if kw_in_text(kw, t):
            return 'comp'
    for g in ('own', 'comp', 'ind'):
        if query_kw in kw_groups[g]:
            return g
    return 'ind'


def keyword_relevant(kw, title, desc):
    """짧은 영문 약어(PF, IB 등)는 단어 경계로 엄격히 확인하여 잡음을 줄임"""
    text = f"{title} {desc}"
    if re.fullmatch(r'[A-Za-z0-9 .&]{1,4}', kw.strip()):
        return re.search(r'(?<![A-Za-z0-9])' + re.escape(kw.strip()) + r'(?![A-Za-z0-9])', text, re.I) is not None
    return True


def compute_quick_rank(item, kw_all, core_kw):
    title_l = (item.get('title') or '').lower()
    press = item.get('press', '')
    tier = press_tier(press)
    tier_score = 38 if tier == 1 else (28 if tier == 2 else 14)
    matched_cnt = sum(1 for k in kw_all if k and k.lower() in title_l)
    kw_score = min(36, 12 + matched_cnt * 10)
    if core_kw and any(k.lower() in title_l for k in core_kw):
        kw_score += 12
    return tier_score + kw_score


# ---------------------------------------------------------------------------
# 네이버 검색 API
# ---------------------------------------------------------------------------
class NaverAuthError(Exception):
    """인증/권한 오류 - 재시도해도 소용없으므로 이번 실행에서 네이버 사용을 중단"""


def _read_http_error(e):
    try:
        body = e.read().decode('utf-8', errors='replace')
        j = json.loads(body)
        return f"HTTP {e.code} errorCode={j.get('errorCode')} message={j.get('errorMessage')}"
    except Exception:
        return f"HTTP {e.code}"


class NaverClient:
    OPENAPI = "https://openapi.naver.com/v1/search/news.json"
    HUB = "https://naveropenapi.apigw.ntruss.com/search/v1/news.json"

    def __init__(self, client_id, client_secret):
        self.cid = client_id
        self.secret = client_secret
        self.base = 'openapi'
        self.calls = 0

    def _build(self, base, query, display, start):
        q = urllib.parse.quote(query)
        if base == 'openapi':
            req = urllib.request.Request(f"{self.OPENAPI}?query={q}&display={display}&start={start}&sort=date")
            req.add_header("X-Naver-Client-Id", self.cid)
            req.add_header("X-Naver-Client-Secret", self.secret)
        else:
            req = urllib.request.Request(f"{self.HUB}?query={q}&display={display}&start={start}&sort=date")
            req.add_header("X-NCP-APIGW-API-KEY-ID", self.cid)
            req.add_header("X-NCP-APIGW-API-KEY", self.secret)
        return req

    def _call(self, base, query, display, start):
        last = None
        for attempt in range(3):
            try:
                self.calls += 1
                with urllib.request.urlopen(self._build(base, query, display, start), timeout=12) as resp:
                    return json.loads(resp.read().decode('utf-8')).get('items', [])
            except urllib.error.HTTPError as e:
                detail = _read_http_error(e)
                if e.code in (401, 403):
                    raise NaverAuthError(f"[{base}] {detail}")
                last = RuntimeError(f"[{base}] {detail}")
                if e.code == 429 or e.code >= 500:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise last
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last = RuntimeError(f"[{base}] 네트워크 오류: {e}")
                time.sleep(1.0 * (attempt + 1))
        raise last or RuntimeError("알 수 없는 네이버 API 오류")

    def search(self, query, display=100, start=1):
        try:
            return self._call(self.base, query, display, start)
        except NaverAuthError as first:
            # 일반 개발자센터 키로 실패하면 NCP 게이트웨이 방식으로 한 번 더 시도
            if self.base == 'openapi':
                try:
                    items = self._call('hub', query, display, start)
                    self.base = 'hub'
                    return items
                except NaverAuthError:
                    pass
            raise first


# ---------------------------------------------------------------------------
# 구글 뉴스 RSS (보조)
# ---------------------------------------------------------------------------
def fetch_google_rss_fallback(query, start_dt, end_dt):
    after_str = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    before_str = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    full_q = f'{query} after:{after_str} before:{before_str}'
    encoded = urllib.parse.quote(full_q)
    rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(rss_url, headers={"User-Agent": UA_HEADER["User-Agent"]})
    with urllib.request.urlopen(req, timeout=12) as resp:
        xml_data = resp.read().decode('utf-8')

    root = ET.fromstring(xml_data)
    items_out = []
    for item in root.findall('.//item'):
        raw_title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        pub_date = (item.findtext('pubDate') or '').strip()
        source_el = item.find('source')
        press = source_el.text.strip() if (source_el is not None and source_el.text) else ''
        clean_t = raw_title
        dash_idx = raw_title.rfind(' - ')
        if dash_idx > 0:
            clean_t = raw_title[:dash_idx].strip()
            if not press:
                press = raw_title[dash_idx + 3:].strip()
        items_out.append({
            'title': clean_t,
            'originallink': link,
            'pubDate': pub_date,
            'customPress': press or '주요언론',
            'description': ''
        })
    return items_out


# ---------------------------------------------------------------------------
# 수집 기간 / 대상 계열사
# ---------------------------------------------------------------------------
def get_date_bounds(now_dt, start_str, end_str):
    start_dt = None
    end_dt = None
    if start_str:
        try:
            d = datetime.strptime(start_str.strip(), '%Y-%m-%d')
            start_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=KST)
        except Exception:
            pass
    if end_str:
        try:
            d = datetime.strptime(end_str.strip(), '%Y-%m-%d')
            end_dt = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=KST)
        except Exception:
            pass

    if start_dt or end_dt:
        if not start_dt:
            start_dt = end_dt - timedelta(days=3)
        if not end_dt:
            end_dt = now_dt
        return start_dt, end_dt, f"{start_dt.strftime('%Y.%m.%d')} ~ {end_dt.strftime('%Y.%m.%d')}", True

    # 기본: 전일 00:00 ~ 현재 (월요일은 금요일 00:00부터 = 주말 포함)
    back_days = 3 if now_dt.weekday() == 0 else 1
    s = now_dt - timedelta(days=back_days)
    start_dt = datetime(s.year, s.month, s.day, 0, 0, 0, tzinfo=KST)
    return start_dt, now_dt, f"{start_dt.strftime('%Y.%m.%d')} ~ {now_dt.strftime('%Y.%m.%d')}", False


def resolve_targets(target, schedule, now_dt, available):
    target = (target or 'all').strip()
    if target != 'all':
        return [target] if target in available else []
    if schedule == CRON_MORNING_SANGSANGIN:
        picked = ['sangsangin']
    elif schedule == CRON_MORNING_AFFILIATES:
        picked = ['mitech', 'synergy', 'medica']
        if now_dt.weekday() == 4:      # 뉴로바이오젠은 주 1회(금요일)
            picked.append('neurobiogen')
    else:
        picked = list(available)
    return [a for a in picked if a in available]


# ---------------------------------------------------------------------------
# 수집 (scrape)
# ---------------------------------------------------------------------------
def collect_for_affiliate(aff_key, kw_groups, naver, state, start_dt, end_dt, now_dt, history_set, diag):
    all_kws = []
    for g in ('own', 'comp', 'ind'):
        all_kws.extend(kw_groups[g])
    all_kws = list(dict.fromkeys(all_kws))
    kw_flat_lower = all_kws
    collected = []
    seen_norms = set()
    seq = 0

    for kw in all_kws:
        items = []
        src = None
        if naver and not state['naver_disabled']:
            try:
                page = 1
                while page <= 3:
                    batch = naver.search(kw, display=100, start=(page - 1) * 100 + 1)
                    items.extend(batch)
                    if len(batch) < 100:
                        break
                    # 100건이 모두 기간 안이면 다음 페이지도 조회
                    try:
                        oldest = parsedate_to_datetime(batch[-1].get('pubDate', '')).astimezone(KST)
                        if oldest < start_dt:
                            break
                    except Exception:
                        break
                    page += 1
                src = 'naver'
                diag['naverKeywordsOk'] += 1
            except NaverAuthError as e:
                state['naver_disabled'] = True
                diag['authError'] = str(e)
                warn(f"네이버 API 인증/권한 오류로 이번 실행에서 네이버를 중단합니다: {e}")
                items = []
            except Exception as e:
                diag['naverKeywordsFailed'] += 1
                if len(diag['errors']) < 8:
                    diag['errors'].append(f"{aff_key}/{kw}: {e}")
                log(f"  [WARN] 네이버 실패 ({aff_key}/{kw}): {e}")
                items = []

        if src is None:
            try:
                items = fetch_google_rss_fallback(kw, start_dt, end_dt)
                src = 'google'
                diag['googleKeywords'] += 1
            except Exception as e:
                diag['googleFailed'] += 1
                if len(diag['errors']) < 8:
                    diag['errors'].append(f"{aff_key}/{kw} (google): {e}")
                log(f"  [WARN] 구글 보조 수집 실패 ({aff_key}/{kw}): {e}")
                continue

        for item in items:
            title = clean_html(item.get('title', ''))
            desc = clean_html(item.get('description', ''))
            orig_link = item.get('originallink') or item.get('link') or ''
            naver_link = item.get('link', '') if 'naver.com' in (item.get('link', '') or '') else ''
            pub_raw = item.get('pubDate', '')
            if not title or not orig_link:
                continue
            if not keyword_relevant(kw, title, desc):
                continue
            try:
                pub_dt = parsedate_to_datetime(pub_raw).astimezone(KST)
            except Exception:
                continue
            if pub_dt < start_dt or pub_dt > end_dt:
                continue

            norm = normalize_title(title)
            if not norm or norm in seen_norms:
                continue
            seen_norms.add(norm)

            seq += 1
            press_name = item.get('customPress') or extract_press(orig_link)
            art = {
                "id": int(now_dt.timestamp() * 1000) + seq,
                "category": classify(title, desc, kw, kw_groups),
                "press": press_name,
                "title": title,
                "url": orig_link,
                "pubDateISO": pub_dt.isoformat(),
                "time": pub_dt.strftime('%Y.%m.%d %H:%M'),
                "pubTs": pub_dt.timestamp(),
                "matchedKw": kw,
                "source": src,
                "duplicate": norm in history_set,
                "selected": False
            }
            if naver_link:
                art["naverUrl"] = naver_link
            if desc:
                art["summary"] = desc[:200]
            collected.append(art)
        time.sleep(0.05)

    core = kw_groups['own']
    for a in collected:
        a['rank'] = compute_quick_rank(a, kw_flat_lower, core)
    collected.sort(key=lambda x: (-x['rank'], -x['pubTs']))

    # 풀 용량 제한: 자사 기사는 모두 유지, 나머지는 추천 순위 상위만
    own = [a for a in collected if a['category'] == 'own']
    rest = [a for a in collected if a['category'] != 'own']
    keep = own + rest[:max(0, POOL_CAP_PER_AFFILIATE - len(own))]
    keep.sort(key=lambda x: (-x['rank'], -x['pubTs']))
    return keep, len(collected)


def update_stats(stats, date_key, aff_key, articles):
    press_cnt, kw_cnt = {}, {}
    cat = {'own': 0, 'comp': 0, 'ind': 0}
    for a in articles:
        cat[a['category']] = cat.get(a['category'], 0) + 1
        press_cnt[a['press']] = press_cnt.get(a['press'], 0) + 1
        kw_cnt[a['matchedKw']] = kw_cnt.get(a['matchedKw'], 0) + 1
    top = lambda d, n: dict(sorted(d.items(), key=lambda x: -x[1])[:n])
    stats.setdefault('days', {}).setdefault(date_key, {})[aff_key] = {
        'total': len(articles), 'own': cat['own'], 'comp': cat['comp'], 'ind': cat['ind'],
        'press': top(press_cnt, 8), 'kw': top(kw_cnt, 8)
    }
    cutoff = (datetime.now(KST) - timedelta(days=RETENTION_DAYS)).strftime('%Y-%m-%d')
    stats['days'] = {d: v for d, v in stats['days'].items() if d >= cutoff}


def run_scrape():
    now_dt = datetime.now(KST)
    target = os.environ.get("TARGET_AFFILIATE", "all")
    schedule = os.environ.get("SCHEDULE_CRON", "").strip()
    client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    start_str = os.environ.get("START_DATE", "").strip()
    end_str = os.environ.get("END_DATE", "").strip()

    pool_data = load_json(POOL_FILE, {"updatedAt": "", "keywords": {}, "affiliates": {}})
    pub_data = load_json(PUBLISHED_FILE, {"history": {}, "published": {}})
    all_keywords = load_keywords(pool_data)
    if not all_keywords:
        log("[ERROR] keywords.json 에서 키워드를 찾을 수 없습니다.")
        return 1

    targets = resolve_targets(target, schedule, now_dt, list(all_keywords.keys()))
    if not targets:
        log(f"[INFO] 이번 실행 대상 계열사가 없습니다. (target={target}, schedule={schedule})")
        return 0

    start_dt, end_dt, range_label, explicit_range = get_date_bounds(now_dt, start_str, end_str)

    naver = None
    if client_id and client_secret:
        naver = NaverClient(client_id, client_secret)
        log(f"[INFO] 네이버 API 키 감지됨 (ID 길이 {len(client_id)}, Secret 길이 {len(client_secret)})")
    else:
        warn("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 비어 있어 구글 보조 수집만 가능합니다. GitHub Secrets를 확인하세요.")

    state = {'naver_disabled': naver is None}
    diag = {'naverKeywordsOk': 0, 'naverKeywordsFailed': 0, 'googleKeywords': 0, 'googleFailed': 0,
            'authError': '' if naver else 'API 키 미설정', 'errors': []}

    history_map = pub_data.get("history", {})
    affiliates_out = pool_data.get("affiliates", {})
    stats = load_json(STATS_FILE, {"days": {}})
    zero_targets = []
    log(f"[INFO] 대상: {targets} / 기간: {range_label}")

    for aff_key in targets:
        collected, total_found = collect_for_affiliate(
            aff_key, all_keywords[aff_key], naver, state, start_dt, end_dt, now_dt,
            set(history_map.get(aff_key, [])), diag)
        n_naver = sum(1 for a in collected if a.get('source') == 'naver')
        n_google = len(collected) - n_naver
        used = f"NAVER API {n_naver}건 / Google 보조 {n_google}건"
        affiliates_out[aff_key] = {
            "scrapedAt": f"{now_dt.strftime('%Y-%m-%d %H:%M:%S KST')} ({used})",
            "dateRange": range_label,
            "count": len(collected),
            "articles": collected
        }
        log(f"[OK] {aff_key}: {len(collected)}건 저장 (수집 {total_found}건 중) - {used}")
        if len(collected) == 0:
            zero_targets.append(aff_key)
            warn(f"{aff_key}: 수집된 기사가 0건입니다.")
        if not explicit_range:
            update_stats(stats, now_dt.strftime('%Y-%m-%d'), aff_key, collected)

    pool_data["updatedAt"] = now_dt.strftime('%Y-%m-%d %H:%M:%S KST')
    pool_data["keywords"] = {k: v for k, v in all_keywords.items()}
    pool_data["affiliates"] = affiliates_out
    pool_data["diagnostics"] = {
        "runAt": pool_data["updatedAt"], "targets": targets, "range": range_label,
        "naverConfigured": bool(naver), "naverApiCalls": naver.calls if naver else 0,
        **diag
    }
    save_json(POOL_FILE, pool_data)
    if not explicit_range:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        save_json(STATS_FILE, stats)
    if not os.path.exists(PUBLISHED_FILE):
        save_json(PUBLISHED_FILE, pub_data)

    log("---- 수집 진단 ----")
    log(json.dumps(pool_data["diagnostics"], ensure_ascii=False, indent=2))

    # 알림용 종료 코드: 대상 전체가 0건이거나 네이버 인증 실패 + 보조 수집도 실패한 경우 워크플로를 실패 처리
    if zero_targets and len(zero_targets) == len(targets):
        log("[FAIL] 모든 대상 계열사에서 0건이 수집되었습니다.")
        return 2
    return 0


# ---------------------------------------------------------------------------
# 아카이브 (archive)
# ---------------------------------------------------------------------------
def fetch_page_meta(url):
    """기사 페이지에서 대표 이미지(og:image)와 요약(og:description)만 가볍게 추출"""
    out = {"image": "", "summary": ""}
    try:
        req = urllib.request.Request(url, headers=UA_HEADER)
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read(250000)
            charset = resp.headers.get_content_charset()
            if not charset:
                head = raw[:2048].decode('ascii', errors='ignore').lower()
                charset = 'cp949' if ('euc-kr' in head or 'ks_c_5601' in head) else 'utf-8'
            page = raw.decode(charset, errors='replace')
        p = MetaTagParser()
        try:
            p.feed(page)
        except Exception:
            pass
        img = p.meta.get('og:image') or p.meta.get('twitter:image') or ''
        if img:
            img = html.unescape(img).strip()
            if img.startswith('//'):
                img = 'https:' + img
            elif img.startswith('/'):
                u = urllib.parse.urlparse(url)
                img = f"{u.scheme}://{u.netloc}{img}"
            if img.startswith('http') and 'google' not in img.lower():
                out["image"] = img
        desc = p.meta.get('og:description') or p.meta.get('description') or ''
        if desc:
            out["summary"] = clean_html(desc)[:200]
    except Exception:
        pass
    return out


def enrich_one(art):
    url = art.get('url', '')
    if not url:
        return
    real = art.get('realUrl') or url
    if 'news.google.com' in real:
        real = resolve_google_news_url(real, title=art.get('title', ''), press=art.get('press', ''))
        if 'news.google.com' not in real:
            art['realUrl'] = real
    if 'news.google.com' in real:
        art['metaTried'] = True
        return
    meta = fetch_page_meta(real)
    if meta['image']:
        art['image'] = meta['image']
    if meta['summary'] and not art.get('summary'):
        art['summary'] = meta['summary']
    art['metaTried'] = True


def date_iso(d):
    return (d or '').strip().replace('.', '-')


def run_archive():
    pub = load_json(PUBLISHED_FILE, {"history": {}, "published": {}})
    published = pub.get('published', {})
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 1) 아직 메타 정보를 확인하지 않은 발행 기사만 보강 (SKIP_ENRICH=1 이면 생략)
    targets = []
    if os.environ.get('SKIP_ENRICH') != '1':
        for entry in published.values():
            for art in entry.get('articles', []):
                if not art.get('metaTried'):
                    targets.append(art)
    if targets:
        log(f"[INFO] 대표 이미지/요약 보강 대상 {len(targets)}건")
        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(enrich_one, targets))
        save_json(PUBLISHED_FILE, pub)

    # 2) 발행분을 날짜별 파일에 병합
    for aff, entry in published.items():
        d = date_iso(entry.get('date'))
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d):
            continue
        path = os.path.join(ARCHIVE_DIR, f"{d}.json")
        day = load_json(path, {"date": d, "affiliates": {}})
        day.setdefault('affiliates', {})[aff] = {
            "name": entry.get('name', aff),
            "manager": entry.get('manager', ''),
            "date": entry.get('date', ''),
            "quote": entry.get('quote', ''),
            "author": entry.get('author', ''),
            "articles": entry.get('articles', [])
        }
        day['date'] = d
        save_json(path, day)

    # 3) 보관기간 초과분 삭제
    cutoff = (datetime.now(KST) - timedelta(days=RETENTION_DAYS)).strftime('%Y-%m-%d')
    for path in glob.glob(os.path.join(ARCHIVE_DIR, '????-??-??.json')):
        if os.path.basename(path)[:10] < cutoff:
            os.remove(path)
            log(f"[INFO] 보관기간 초과 삭제: {path}")

    # 4) 인덱스 / 검색 인덱스 재생성
    index = {}
    search = []
    for path in sorted(glob.glob(os.path.join(ARCHIVE_DIR, '????-??-??.json')), reverse=True):
        day = load_json(path, None)
        if not day:
            continue
        d = day['date']
        for aff, e in day.get('affiliates', {}).items():
            if not e.get('articles'):
                continue
            index.setdefault(aff, []).append(d)
            for a in e['articles']:
                search.append({"d": d, "a": aff, "c": a.get('category', 'ind'), "p": a.get('press', ''),
                               "t": a.get('title', ''), "u": a.get('realUrl') or a.get('url', '')})
    save_json(INDEX_FILE, {"updatedAt": datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST'),
                           "retentionDays": RETENTION_DAYS, "dates": index})
    with open(SEARCH_FILE, 'w', encoding='utf-8') as f:
        json.dump(search, f, ensure_ascii=False, separators=(',', ':'))
    log(f"[OK] 아카이브 갱신: 날짜 {sum(len(v) for v in index.values())}건(계열사별), 검색 인덱스 {len(search)}건")
    return 0


def main():
    mode = os.environ.get("RUN_MODE", "scrape").strip()
    if mode in ("archive", "enrich_published"):
        return run_archive()
    return run_scrape()


if __name__ == '__main__':
    sys.exit(main())
