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
AFFILIATE_ORDER = ['sangsangin', 'mitech', 'synergy', 'medica', 'neurobiogen', 'csr']
# 주 1회 발행하는 구분값: 기본 수집 기간이 '최근 7일', 일별 통계(급증 배지)에서는 제외
WEEKLY_AFFILIATES = {'neurobiogen', 'csr'}

DAILY_AFFILIATES = ['sangsangin', 'mitech', 'synergy', 'medica']   # 매 영업일 발행
CUTOFF_HOUR = 6            # 자동 수집의 종료 시각: 당일 오전 6시 30분 (이후 기사는 다음 수집에 포함)
CUTOFF_MINUTE = 30
HOLIDAY_FILE = 'holidays.json'   # {"add": ["YYYY-MM-DD"...], "remove": [...]} 회사 휴무일 추가/공휴일이지만 근무하는 날 제외
# 'holidays' 패키지를 설치하지 못했을 때를 위한 비상용 목록 (2026~2027)
FALLBACK_HOLIDAYS = {
    '2026-01-01': '신정', '2026-02-16': '설날 연휴', '2026-02-17': '설날', '2026-02-18': '설날 연휴',
    '2026-03-01': '삼일절', '2026-03-02': '삼일절 대체공휴일', '2026-05-01': '노동절', '2026-05-05': '어린이날',
    '2026-05-24': '부처님오신날', '2026-05-25': '부처님오신날 대체공휴일', '2026-06-03': '지방선거일',
    '2026-06-06': '현충일', '2026-07-17': '제헌절', '2026-08-15': '광복절', '2026-08-17': '광복절 대체공휴일',
    '2026-09-24': '추석 연휴', '2026-09-25': '추석', '2026-09-26': '추석 연휴', '2026-10-03': '개천절',
    '2026-10-05': '개천절 대체공휴일', '2026-10-09': '한글날', '2026-12-25': '성탄절',
    '2027-01-01': '신정', '2027-02-06': '설날 연휴', '2027-02-07': '설날', '2027-02-08': '설날 연휴',
    '2027-02-09': '설날 대체공휴일', '2027-03-01': '삼일절', '2027-05-01': '노동절', '2027-05-03': '노동절 대체공휴일',
    '2027-05-05': '어린이날', '2027-05-13': '부처님오신날', '2027-06-06': '현충일', '2027-07-17': '제헌절',
    '2027-07-19': '제헌절 대체공휴일', '2027-08-15': '광복절', '2027-08-16': '광복절 대체공휴일',
    '2027-09-14': '추석 연휴', '2027-09-15': '추석', '2027-09-16': '추석 연휴', '2027-10-03': '개천절',
    '2027-10-04': '개천절 대체공휴일', '2027-10-09': '한글날', '2027-10-11': '한글날 대체공휴일',
    '2027-12-25': '성탄절', '2027-12-27': '성탄절 대체공휴일',
}

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


# keywords.json 에 아직 없는 구분값(사회공헌)은 아래 기본 키워드로 수집합니다. (관리자 ▸ 키워드 탭에서 저장하면 keywords.json 이 우선)
DEFAULT_KEYWORDS = {
    'csr': {
        'own': ['휠체어', '이동권', '자립지원', '조직문화 사회공헌', '임직원 참여 사회공헌'],
        'comp': ['비즈니스 기반 사회공헌', '지역사회 사회공헌', 'IT 사회공헌', '의료 사회공헌'],
        'ind': ['사회공헌', 'CSR', '소셜임팩트', '임직원 봉사활동', 'ESG 사회공헌', '사회적가치'],
    }
}


def load_keywords(pool_data):
    raw = load_json(KEYWORD_FILE, None)
    if not raw:
        raw = (pool_data or {}).get('keywords') or {}
    result = {}
    for aff in AFFILIATE_ORDER:
        if aff in raw:
            result[aff] = normalize_keywords(raw[aff])
        elif aff in DEFAULT_KEYWORDS:
            result[aff] = normalize_keywords(DEFAULT_KEYWORDS[aff])
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
    """HTTP 오류 본문을 사람이 읽을 수 있게 요약 (개발자센터/NAVER API HUB 응답 형식 모두 대응)"""
    try:
        body = e.read().decode('utf-8', errors='replace').strip()
    except Exception:
        return f"HTTP {e.code}"
    try:
        j = json.loads(body)
        err = j.get('error') if isinstance(j.get('error'), dict) else j
        code = err.get('errorCode') or err.get('code')
        msg = err.get('errorMessage') or err.get('message')
        if code or msg:
            return f"HTTP {e.code} errorCode={code} message={msg}"
    except Exception:
        pass
    return f"HTTP {e.code} {body[:160]}" if body else f"HTTP {e.code}"


class NaverClient:
    # 현재 표준: 네이버 클라우드 플랫폼 NAVER API HUB (개발자센터 검색 API는 여기로 이관됨)
    HUB = "https://naverapihub.apigw.ntruss.com/search/v1/news"
    # 이전 방식(개발자센터 발급 키) - 예전 키가 남아 있는 경우만 보조로 사용
    OPENAPI = "https://openapi.naver.com/v1/search/news.json"

    def __init__(self, client_id, client_secret):
        self.cid = client_id
        self.secret = client_secret
        self.base = 'hub'
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
            # NAVER API HUB 키로 실패하면, 예전 개발자센터 키일 가능성을 생각해 한 번 더 시도
            if self.base == 'hub':
                try:
                    items = self._call('openapi', query, display, start)
                    self.base = 'openapi'
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
# ---------------------------------------------------------------------------
# 영업일 · 공휴일 · 수집 기간 계산
# ---------------------------------------------------------------------------
def load_holidays(year):
    """{date: 이름} - 대한민국 공휴일(대체공휴일 포함) + 회사 휴무일(holidays.json 의 add) - 근무일 지정(remove)"""
    names = {}
    try:
        import holidays as _hol
        for d, n in _hol.KR(years=[year - 1, year, year + 1]).items():
            names[d] = str(n)
    except Exception as e:
        warn(f"공휴일 패키지를 불러오지 못해 내장 목록(2026~2027)을 사용합니다: {e}")
        for d, n in FALLBACK_HOLIDAYS.items():
            names[datetime.strptime(d, '%Y-%m-%d').date()] = n
    cfg = load_json(HOLIDAY_FILE, {}) or {}
    for key, add in (('add', True), ('remove', False)):
        for ds in cfg.get(key, []) or []:
            try:
                d = datetime.strptime(str(ds).strip()[:10], '%Y-%m-%d').date()
            except Exception:
                continue
            if add:
                names[d] = '회사 휴무일'
            else:
                names.pop(d, None)
    return names


def is_business_day(d, hol):
    return d.weekday() < 5 and d not in hol


def prev_business_day(d, hol):
    x = d - timedelta(days=1)
    for _ in range(30):
        if is_business_day(x, hol):
            return x
        x -= timedelta(days=1)
    return d - timedelta(days=1)


def weekly_run_day(d, hol):
    """그 주(월~금)의 마지막 영업일. 보통 금요일이고, 금요일이 휴일이면 앞선 영업일"""
    monday = d - timedelta(days=d.weekday())
    days = [monday + timedelta(days=i) for i in range(5)]
    biz = [x for x in days if is_business_day(x, hol)]
    return biz[-1] if biz else None


def day_start(d):
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=KST)


def auto_window(aff_key, now_dt, hol, scheduled):
    """자동 수집 기간
    - 매일 발행(상상인·엠아이텍·시너지이노베이션·메디카코리아): 직전 영업일 00:00 ~ 오늘 오전 6시 30분
      (화: 월 00:00~화 06:30 / 월: 금 00:00~월 06:30 / 연휴 다음 영업일: 연휴 직전 영업일 00:00부터)
    - 주 1회 발행(뉴로바이오젠·사회공헌): 지난주 같은 요일 00:00 ~ 오늘 오전 6시 30분 (금요일 실행 시 지난 금요일~이번 금요일 6시 30분)
    - 수동 실행은 끝 시각만 '지금'으로 합니다.
    """
    today = now_dt.date()
    if aff_key in WEEKLY_AFFILIATES:
        start = day_start(today - timedelta(days=7))
    else:
        start = day_start(prev_business_day(today, hol))
    cutoff = datetime(today.year, today.month, today.day, CUTOFF_HOUR, CUTOFF_MINUTE, 0, tzinfo=KST)
    end = min(cutoff, now_dt) if scheduled else now_dt
    label = f"{start.strftime('%Y.%m.%d %H:%M')} ~ {end.strftime('%Y.%m.%d %H:%M')}"
    return start, end, label


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


def resolve_targets(target, schedule, now_dt, available, hol=None):
    """수집 대상 결정
    - target: 'all' 이거나, 쉼표로 구분한 계열사 키 목록 (예: 'sangsangin,mitech' / 'neurobiogen' / 'csr')
    - 'all' 이고 자동 실행(schedule)이면: 영업일마다 매일 발행 4곳 + (그 주의 마지막 영업일이면) 뉴로바이오젠·사회공헌
    - 'all' 이고 수동 실행이면 전체
    """
    raw = (target or 'all').strip()
    wanted = [t.strip() for t in re.split(r'[,\s]+', raw) if t.strip()]
    if wanted and 'all' not in wanted:
        seen = []
        for t in wanted:
            if t in available and t not in seen:
                seen.append(t)
        return seen
    if schedule:
        hol = hol if hol is not None else load_holidays(now_dt.year)
        today = now_dt.date()
        picked = []
        if is_business_day(today, hol):
            picked = list(DAILY_AFFILIATES)
            if weekly_run_day(today, hol) == today:
                picked += sorted(WEEKLY_AFFILIATES, key=lambda k: AFFILIATE_ORDER.index(k))
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
            if norm in history_set:          # 이미 발행했던 기사는 후보에서 제외
                diag['dupExcluded'] = diag.get('dupExcluded', 0) + 1
                continue

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

    scheduled = bool(schedule)
    hol = load_holidays(now_dt.year)
    today = now_dt.date()
    if scheduled and not is_business_day(today, hol):
        why = hol.get(today) or ('주말' if today.weekday() >= 5 else '휴무일')
        log(f"[SKIP] 오늘({today}, {why})은 쉬는 날이라 자동 수집을 건너뜁니다. 다음 영업일 수집에서 이 기간까지 함께 모읍니다.")
        return 0
    targets = resolve_targets(target, schedule, now_dt, list(all_keywords.keys()), hol)
    if not targets:
        log(f"[INFO] 이번 실행 대상 계열사가 없습니다. (target={target}, schedule={schedule})")
        return 0

    start_dt, end_dt, range_label, explicit_range = get_date_bounds(now_dt, start_str, end_str)
    kind = '자동(매일 06:30)' if scheduled else '수동'

    naver = None
    if client_id and client_secret:
        naver = NaverClient(client_id, client_secret)
        log(f"[INFO] 네이버 API 키 감지됨 (ID 길이 {len(client_id)}, Secret 길이 {len(client_secret)})")
    else:
        warn("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 비어 있어 구글 보조 수집만 가능합니다. GitHub Secrets를 확인하세요.")

    state = {'naver_disabled': naver is None}
    diag = {'naverKeywordsOk': 0, 'naverKeywordsFailed': 0, 'googleKeywords': 0, 'googleFailed': 0,
            'authError': '' if naver else 'API 키 미설정', 'errors': [], 'dupExcluded': 0}

    history_map = pub_data.get("history", {})
    affiliates_out = pool_data.get("affiliates", {})
    stats = load_json(STATS_FILE, {"days": {}})
    zero_targets = []
    windows = {}
    log(f"[INFO] {kind} 수집 / 대상: {targets}")

    for aff_key in targets:
        if explicit_range:
            a_start, a_end, a_label = start_dt, end_dt, range_label
        else:
            a_start, a_end, a_label = auto_window(aff_key, now_dt, hol, scheduled)
        windows[aff_key] = a_label
        log(f"[INFO] {aff_key} 수집 기간: {a_label}")
        collected, total_found = collect_for_affiliate(
            aff_key, all_keywords[aff_key], naver, state, a_start, a_end, now_dt,
            set(history_map.get(aff_key, [])), diag)
        n_naver = sum(1 for a in collected if a.get('source') == 'naver')
        n_google = len(collected) - n_naver
        used = f"NAVER API {n_naver}건 / Google 보조 {n_google}건"
        # 관리자가 URL로 직접 추가한 기사(최근 3일)는 재수집해도 후보에 남겨 둡니다
        kept_manual = keep_recent_manual((affiliates_out.get(aff_key) or {}).get('articles', []), now_dt, collected)
        if kept_manual:
            collected = kept_manual + collected
        affiliates_out[aff_key] = {
            "scrapedAt": f"{now_dt.strftime('%Y-%m-%d %H:%M:%S KST')} ({used})",
            "dateRange": a_label,
            "count": len(collected),
            "articles": collected
        }
        log(f"[OK] {aff_key}: {len(collected)}건 저장 (수집 {total_found}건 중) - {used}")
        if len(collected) == 0:
            zero_targets.append(aff_key)
            warn(f"{aff_key}: 수집된 기사가 0건입니다.")
        if not explicit_range and aff_key not in WEEKLY_AFFILIATES:
            update_stats(stats, now_dt.strftime('%Y-%m-%d'), aff_key, collected)
        log(f"  → 이미 발행한 기사 제외 누계: {diag.get('dupExcluded', 0)}건")

    pool_data["updatedAt"] = now_dt.strftime('%Y-%m-%d %H:%M:%S KST')
    pool_data["keywords"] = {k: v for k, v in all_keywords.items()}
    pool_data["affiliates"] = affiliates_out
    # 네이버 API 호출 횟수 누계 (일별, 최근 62일) - 무료 한도 관리용
    usage = pool_data.get("usage") or {}
    today_key = now_dt.strftime('%Y-%m-%d')
    usage[today_key] = usage.get(today_key, 0) + (naver.calls if naver else 0)
    cut = (now_dt - timedelta(days=62)).strftime('%Y-%m-%d')
    pool_data["usage"] = {k: v for k, v in sorted(usage.items()) if k >= cut}
    pool_data["diagnostics"] = {
        "runAt": pool_data["updatedAt"], "mode": kind, "targets": targets, "windows": windows,
        "range": range_label if explicit_range else ' / '.join(f"{k}: {v}" for k, v in windows.items()),
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
# URL로 기사 직접 추가 (관리자 ▸ 후보 기사 ▸ [URL로 기사 추가])
# ---------------------------------------------------------------------------
MANUAL_KEEP_DAYS = 3
MAX_MANUAL_URLS = 10


def keep_recent_manual(old_articles, now_dt, new_articles):
    """이전 풀에서 직접 추가한(manual) 기사 중 최근 N일 이내인 것만 남기고, 새로 수집된 기사와 제목이 겹치면 제외"""
    cutoff = now_dt.timestamp() - MANUAL_KEEP_DAYS * 86400
    have = {normalize_title(a.get('title', '')) for a in new_articles}
    out = []
    for a in old_articles or []:
        if a.get('manual') and a.get('addedTs', 0) >= cutoff and normalize_title(a.get('title', '')) not in have:
            out.append(a)
    return out


class ArticleParser(HTMLParser):
    """제목·메타태그·본문 첫 문단을 한 번에 추출"""
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title = ''
        self.paras = []
        self._in_title = False
        self._skip = 0
        self._in_p = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = {k.lower(): (v or '') for k, v in attrs if k}
        if tag == 'meta':
            key = (a.get('property') or a.get('name') or a.get('itemprop') or '').strip().lower()
            val = a.get('content', '').strip()
            if key and val and key not in self.meta:
                self.meta[key] = val
        elif tag == 'title':
            self._in_title = True
        elif tag in ('script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside', 'form', 'button'):
            self._skip += 1
        elif tag == 'p' and not self._skip:
            self._in_p = True
            self._buf = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'title':
            self._in_title = False
        elif tag in ('script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside', 'form', 'button'):
            self._skip = max(0, self._skip - 1)
        elif tag == 'p' and self._in_p:
            self._in_p = False
            text = re.sub(r'\s+', ' ', ''.join(self._buf)).strip()
            if len(text) >= 40 and len(self.paras) < 8:
                self.paras.append(text)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_p and not self._skip:
            self._buf.append(data)


def _decode_page(raw, headers):
    charset = headers.get_content_charset()
    if not charset:
        head = raw[:4096].decode('ascii', errors='ignore').lower()
        m = re.search(r'charset=["\']?([\w-]+)', head)
        charset = m.group(1) if m else ''
    if charset in ('euc-kr', 'ks_c_5601-1987', 'ksc5601'):
        charset = 'cp949'
    if charset:
        try:
            return raw.decode(charset, errors='replace')
        except LookupError:
            pass
    try:                       # 선언이 없으면 UTF-8 → 실패 시 한국 사이트에 흔한 CP949
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('cp949', errors='replace')


def _parse_meta_date(meta, now_dt):
    for k in ('article:published_time', 'og:article:published_time', 'datepublished', 'pubdate',
              'article:published', 'date', 'dc.date', 'dc.date.issued', 'og:regdate', 'article:modified_time'):
        v = meta.get(k)
        if not v:
            continue
        v = v.strip()
        try:
            dt = datetime.fromisoformat(v.replace('Z', '+00:00').replace(' ', 'T', 1))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt.astimezone(KST)
        except Exception:
            pass
        m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?:\D+(\d{1,2}):(\d{2}))?', v)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                int(m.group(4) or 0), int(m.group(5) or 0), tzinfo=KST)
            except Exception:
                pass
    return now_dt


def first_sentences(text, limit=200):
    """본문 앞부분 1~2문장을 limit 글자 안에서 자연스럽게 자른다"""
    text = re.sub(r'\s+', ' ', clean_html(text or '')).strip()
    # '(서울=연합뉴스) 홍길동 기자 =' 같은 머리말 제거
    text = re.sub(r'^\([^)]{1,25}\)\s*(?=[^.]{0,30}=)', '', text)
    text = re.sub(r'^([가-힣]{2,4}\s*)?(기자|특파원)\s*=\s*', '', text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    m = list(re.finditer(r'[.!?。]|다\s', cut))
    if m and m[-1].end() >= 40:
        return cut[:m[-1].end()].strip()
    return cut.rstrip() + '…'


def clean_article_title(title, press, site_name):
    t = html.unescape(re.sub(r'\s+', ' ', title or '')).strip()
    names = [x for x in (press, site_name) if x]
    for sep in (' - ', ' | ', ' :: ', ' – ', ' : ', ' ㅣ '):
        if sep in t:
            head, tail = t.rsplit(sep, 1)
            if head and (any(n in tail or tail in n for n in names) or tail.endswith('뉴스') or tail.endswith('신문')):
                t = head.strip()
                break
    return t


def fetch_article_meta(url, now_dt):
    """기사 URL → 제목/언론사/요약(첫 문장)/발행시각/대표이미지. 실패 시 ValueError"""
    real = url
    if 'news.google.com' in real:
        real = resolve_google_news_url(real, title='', press='')
        if 'news.google.com' in real:
            raise ValueError('구글 뉴스 링크에서 원문 주소를 찾지 못했습니다. 언론사 기사 주소를 직접 붙여 넣어주세요.')
    req = urllib.request.Request(real, headers=UA_HEADER)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(600000)
            final_url = resp.geturl() or real
            page = _decode_page(raw, resp.headers)
    except urllib.error.HTTPError as e:
        raise ValueError(f'페이지를 열 수 없습니다 (HTTP {e.code}) — 접근이 제한된 사이트일 수 있습니다.')
    except Exception as e:
        raise ValueError(f'페이지를 열 수 없습니다 ({type(e).__name__})')
    p = ArticleParser()
    try:
        p.feed(page)
    except Exception:
        pass
    m = p.meta
    title = m.get('og:title') or m.get('twitter:title') or p.title
    if not title or not title.strip():
        raise ValueError('제목을 찾지 못했습니다.')
    host = urllib.parse.urlparse(final_url).netloc.lower()
    site_name = html.unescape(m.get('og:site_name', '')).strip()
    press = extract_press(final_url)
    if 'naver.com' in host:     # 네이버 뉴스 페이지: 언론사명은 og:article:author('한국경제 | 네이버')에 있음
        au = html.unescape(m.get('og:article:author', '') or m.get('twitter:creator', '')).split('|')[0].strip()
        press = au or site_name or press
    elif site_name and press not in set(DOMAIN_PRESS_MAP.values()):
        press = site_name        # 도메인 매핑에 없는 매체는 사이트 이름을 사용
    title = clean_article_title(title, press, site_name)
    desc = m.get('og:description') or m.get('description') or m.get('twitter:description') or ''
    summary = first_sentences(desc, 200)
    if len(summary) < 25 and p.paras:
        summary = first_sentences(p.paras[0], 200)
    image = html.unescape(m.get('og:image') or m.get('twitter:image') or '').strip()
    if image.startswith('//'):
        image = 'https:' + image
    elif image.startswith('/'):
        u = urllib.parse.urlparse(final_url)
        image = f"{u.scheme}://{u.netloc}{image}"
    if not image.startswith('http'):
        image = ''
    return {
        'title': title, 'press': press or '주요언론', 'summary': summary, 'image': image,
        'url': final_url, 'pub_dt': _parse_meta_date(m, now_dt), 'naver': 'naver.com' in host,
    }


def run_add_urls():
    now_dt = datetime.now(KST)
    aff = os.environ.get('TARGET_AFFILIATE', '').strip().split(',')[0].strip()
    urls = [u.strip() for u in re.split(r'[\s,]+', os.environ.get('ADD_URLS', '')) if u.strip().lower().startswith('http')]
    urls = list(dict.fromkeys(urls))[:MAX_MANUAL_URLS]

    pool_data = load_json(POOL_FILE, {"updatedAt": "", "keywords": {}, "affiliates": {}})
    pub_data = load_json(PUBLISHED_FILE, {"history": {}, "published": {}})
    all_keywords = load_keywords(pool_data)
    if aff not in all_keywords:
        log(f"[ERROR] 알 수 없는 구분값입니다: {aff!r}")
        return 1
    if not urls:
        log("[ERROR] 추가할 URL이 없습니다.")
        return 1

    kw_groups = all_keywords[aff]
    history_set = set(pub_data.get('history', {}).get(aff, []))
    bucket = pool_data.setdefault('affiliates', {}).setdefault(aff, {"scrapedAt": "", "count": 0, "articles": []})
    articles = bucket.setdefault('articles', [])
    results, added = [], 0
    for i, url in enumerate(urls):
        item = {'url': url, 'ok': False, 'title': '', 'error': ''}
        try:
            meta = fetch_article_meta(url, now_dt)
            title = meta['title']
            norm = normalize_title(title)
            art = {
                "id": int(now_dt.timestamp() * 1000) + i,
                "category": classify(title, meta['summary'], '', kw_groups),
                "press": meta['press'], "title": title, "url": meta['url'],
                "pubDateISO": meta['pub_dt'].isoformat(), "time": meta['pub_dt'].strftime('%Y.%m.%d %H:%M'),
                "pubTs": meta['pub_dt'].timestamp(), "matchedKw": "", "source": "manual", "manual": True,
                "srcUrl": url, "addedTs": now_dt.timestamp(), "rank": 999,
                "duplicate": bool(norm) and norm in history_set, "selected": False,
            }
            if meta['summary']:
                art["summary"] = meta['summary']
            if meta['image']:
                art["image"] = meta['image']
            if meta['naver']:
                art["naverUrl"] = meta['url']
            # 같은 제목/주소의 기존 후보는 새 정보로 교체
            articles[:] = [a for a in articles if not (normalize_title(a.get('title', '')) == norm or a.get('url') == art['url'])]
            articles.insert(0, art)
            item.update(ok=True, title=title, press=meta['press'])
            added += 1
            log(f"[OK] 추가: [{meta['press']}] {title}")
        except Exception as e:
            item['error'] = str(e)
            warn(f"추가 실패: {url} — {e}")
        results.append(item)
        time.sleep(0.3)

    bucket['count'] = len(articles)
    pool_data['manualAdd'] = {"runAt": now_dt.strftime('%Y-%m-%d %H:%M:%S KST'), "affiliate": aff, "items": results}
    save_json(POOL_FILE, pool_data)
    log(f"[INFO] 요청 {len(urls)}건 중 {added}건 추가")
    return 0 if added else 2


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
        rec = {
            "name": entry.get('name', aff),
            "manager": entry.get('manager', ''),
            "date": entry.get('date', ''),
            "quote": entry.get('quote', ''),
            "author": entry.get('author', ''),
            "articles": entry.get('articles', [])
        }
        # 사회공헌 주간 리포트 전용 항목(회차·키워드·금주의 코멘트·섹션·인사이트·마무리)도 함께 보관
        for extra in ('report', 'weekLabel', 'fixedKeywords', 'weeklyKeywords', 'comment', 'sections', 'insights', 'closing'):
            if extra in entry:
                rec[extra] = entry[extra]
        day.setdefault('affiliates', {})[aff] = rec
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
    if mode == "addurls":
        return run_add_urls()
    return run_scrape()


if __name__ == '__main__':
    sys.exit(main())
