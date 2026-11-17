import os
import re
import json
import time
import html
import base64
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))
POOL_FILE = 'scraped_pool.json'
PUBLISHED_FILE = 'published_data.json'

DEFAULT_KEYWORDS = {
  "sangsangin": [
    "유준원", "상상인", "상상인증권", "상상인선박기계", "시너지이노베이션",
    "메디카코리아", "엠아이텍", "노비스바이오", "프로톡스", "에스앤지바이오텍", "바스노바",
    "카카오뱅크", "카카오증권", "대신증권", "한화투자증권", "유안타증권", "교보증권",
    "현대차증권", "하이투자증권", "DB 금융투자", "IBK 투자증권", "다올투자증권",
    "유진투자증권", "이베스트투자증권", "부국증권", "SK 증권",
    "리그테이블", "제2금융", "중소형증권", "금융당국", "금감원", "금융감독원",
    "금융위", "한국은행", "한국거래소", "PF", "IB", "투자은행", "MTS", "ELS", "IPO", "ECM"
  ],
  "mitech": [
    "엠아이텍", "M.I.TECH", "MITECH", "에스앤지바이오텍", "S&G 바이오텍", "S&G BIOTEC", "바스노바",
    "보스톤사이언티", "Boston Scientific", "쿡메디칼", "Cook Medical", "태웅메디칼",
    "올림푸스", "펜탁스 메디칼", "후지필름", "파인메딕스", "스텐트", "스탠트",
    "내시경장비", "초음파장비", "의료기기", "담도",
    "식약처", "식품의약품안전처", "보건복지부", "의약품안전나라",
    "의료기기안심책방", "한국의료기기안전정보원", "한국의료기기산업협회", "한국제약바이오협회"
  ],
  "synergy": [
    "시너지이노베이션", "기산바이오", "고마바이오텍", "머크", "Merck",
    "써모피셔사이언티픽", "아미코젠", "아지노모도제넥신 셀리스트", "엑셀세라퓨틱스",
    "배지", "미생물배양", "세포배양",
    "의료기기", "식약처", "보건복지부", "한국의료기기산업협회", "한국의료기기협동조합"
  ],
  "medica": [
    "메디카코리아", "Medica Korea",
    "동국제약", "종근당", "대웅제약", "동아제약", "유한양행",
    "개량신약", "IMD", "약가 인하", "제네릭",
    "한국제약바이오협회", "식품의약품안전처", "의약품안전나라", "한국제약협동조합", "보건복지부"
  ],
  "neurobiogen": [
    "뉴로바이오젠", "neurobiogen", "KDS2010", "티솔라질린",
    "사이렉스", "사일렉스", "비만 치료제", "치매 치료제", "알츠하이머", "비만약", "치매약",
    "식약처", "식품의약품안전처", "보건복지부", "의약품안전나라", "한국제약바이오협회"
  ]
}

DOMAIN_PRESS_MAP = {
    'hankyung.com': '한국경제', 'mk.co.kr': '매일경제', 'sedaily.com': '서울경제',
    'fnnews.com': '파이낸셜뉴스', 'edaily.co.kr': '이데일리', 'mt.co.kr': '머니투데이',
    'asiae.co.kr': '아시아경제', 'heraldcorp.com': '헤럴드경제', 'dt.co.kr': '디지털타임스',
    'etnews.com': '전자신문', 'inews24.com': '아이뉴스24', 'chosun.com': '조선일보',
    'joongang.co.kr': '중앙일보', 'donga.com': '동아일보', 'yna.co.kr': '연합뉴스',
    'newsis.com': '뉴시스', 'news1.kr': '뉴스1', 'einfomax.co.kr': '연합인포맥스',
    'dailypharm.com': '데일리팜', 'medipana.com': '메디파나뉴스', 'newsmp.com': '의약뉴스',
    'bosa.co.kr': '의학신문', 'kpanews.co.kr': '약사공론', 'yakup.com': '약업신문',
    'hitnews.co.kr': '히트뉴스', 'biospectator.com': '바이오스펙테이터', 'docdocdoc.co.kr': '청년의사',
    'dailymedi.com': '데일리메디', 'medicaltimes.com': '메디컬타임즈', 'rapportian.com': '라포르시안',
    'bokuennews.com': '보건뉴스', 'skyedaily.com': '스카이데일리', 'ceoscoredaily.com': 'CEO스코어데일리',
    'sisajournal-e.com': '시사저널e', 'asiatime.co.kr': '아시아타임즈', 'tf.co.kr': '더팩트',
    'm-i.kr': '매일일보'
}

UA_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"
}

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

def extract_press(url):
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        for domain, name in DOMAIN_PRESS_MAP.items():
            if domain in host:
                return name
        parts = host.replace('www.', '').split('.')
        return parts[0] if parts else '주요언론'
    except Exception:
        return '주요언론'

def flatten_keywords(kw_entry):
    if isinstance(kw_entry, list):
        return [k.strip() for k in kw_entry if k and k.strip()]
    if isinstance(kw_entry, dict):
        merged = []
        for k in ['own', 'comp', 'ind']:
            merged.extend(kw_entry.get(k, []))
        return list(dict.fromkeys([x.strip() for x in merged if x and x.strip()]))
    return []

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
        return start_dt, end_dt, f"{start_dt.strftime('%Y.%m.%d')} ~ {end_dt.strftime('%Y.%m.%d')}"

    start_dt = now_dt - timedelta(days=7)
    return start_dt, now_dt, f"{start_dt.strftime('%Y.%m.%d')} ~ {now_dt.strftime('%Y.%m.%d')} (최근 7일)"

def resolve_google_news_url(gnews_url):
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

    # 방법 2: 신형 Google News 토큰 -> signature/timestamp 획득 후 batchexecute API로 실제 URL 해석
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
                    return m_real.group(1).replace('\\u003d', '=').replace('\\u0026', '&')
    except Exception as e:
        print(f"[WARN] Google News URL 디코딩 실패 ({article_token[:16]}...): {e}")

    return gnews_url

def extract_article_reader_content(url):
    resolved_url = resolve_google_news_url(url)
    print(f"[INFO] 본문 추출 대상 URL: {resolved_url}")
    result = {
        "realUrl": resolved_url,
        "image": "",
        "body": "",
        "summary": ""
    }
    if 'news.google.com' in resolved_url:
        return result

    try:
        req = urllib.request.Request(resolved_url, headers=UA_HEADER)
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw_bytes = resp.read()
            charset = resp.headers.get_content_charset()
            if not charset:
                head_snippet = raw_bytes[:2048].decode('ascii', errors='ignore').lower()
                if 'euc-kr' in head_snippet or 'ks_c_5601' in head_snippet:
                    charset = 'cp949'
                else:
                    charset = 'utf-8'
            try:
                page_html = raw_bytes.decode(charset, errors='replace')
            except Exception:
                page_html = raw_bytes.decode('utf-8', errors='replace')

        # 1. HTMLParser로 안전하게 대표 이미지(og:image) 및 요약(og:description) 추출
        parser = MetaTagParser()
        try:
            parser.feed(page_html)
        except Exception:
            pass

        raw_img = parser.meta.get('og:image') or parser.meta.get('twitter:image') or ''
        if raw_img:
            img_url = html.unescape(raw_img).strip()
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                parsed = urllib.parse.urlparse(resolved_url)
                img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
            if img_url.startswith('http') and 'google' not in img_url.lower():
                result["image"] = img_url

        raw_desc = parser.meta.get('og:description') or parser.meta.get('description') or ''
        if raw_desc:
            result["summary"] = clean_html(raw_desc)

        # 2. 광고·메뉴·스크립트 제거 후 순수 기사 본문 문단 추출
        cleaned = re.sub(r'<(script|style|nav|header|footer|aside|iframe|form|noscript|svg)[^>]*>.*?</\1>', ' ', page_html, flags=re.S | re.I)
        cleaned = re.sub(r'<!--.*?-->', ' ', cleaned, flags=re.S)
        cleaned = re.sub(r'<br\s*/?>', '\n', cleaned, flags=re.I)
        cleaned = re.sub(r'</(p|div|li|h[1-6]|article|section)>', '\n', cleaned, flags=re.I)
        plain = re.sub(r'<[^>]+>', ' ', cleaned)
        plain = html.unescape(plain)

        paragraphs = []
        noise_patterns = re.compile(
            r'(무단\s*전재|재배포\s*금지|저작권자|구독하기|좋아요|기사제보|기자\s*=|Copyright|All rights reserved|로그인|회원가입|댓글\s*\d+|관련기사|많이\s*본\s*뉴스|이\s*기사와\s*함께|이전기사|다음기사|맨위로|프린트|글자크기|기사원문|공유하기|북마크)',
            re.I
        )

        for line in plain.splitlines():
            line = re.sub(r'[ \t\r\f\v]+', ' ', line).strip()
            if len(line) < 35:
                continue
            if noise_patterns.search(line):
                continue
            if re.search(r'[가-힣]{4,}', line):
                paragraphs.append(line)

        dedup_paras = list(dict.fromkeys(paragraphs))
        body_text = "\n\n".join(dedup_paras[:20])
        if len(body_text) > 3800:
            body_text = body_text[:3800] + "..."

        result["body"] = body_text
        print(f"[OK] 추출 결과 -> 이미지: {'있음' if result['image'] else '없음'}, 본문 길이: {len(body_text)}자")
    except Exception as e:
        print(f"[WARN] 본문 추출 예외 ({resolved_url}): {e}")

    return result

def enrich_published_articles(target_affiliate="all"):
    pub_data = load_json(PUBLISHED_FILE, {"history": {}, "published": {}})
    published_map = pub_data.get("published", {})
    updated_count = 0

    for aff_key, entry in published_map.items():
        if target_affiliate != "all" and target_affiliate != aff_key:
            continue
        articles = entry.get("articles", [])
        for art in articles:
            if art.get("readerReady") and (art.get("body") or art.get("image")):
                continue
            url = art.get("url", "")
            if not url:
                continue
            extracted = extract_article_reader_content(url)
            if extracted["realUrl"]:
                art["realUrl"] = extracted["realUrl"]
            if extracted["image"]:
                art["image"] = extracted["image"]
            if extracted["body"]:
                art["body"] = extracted["body"]
            if extracted["summary"]:
                art["summary"] = extracted["summary"]
            art["readerReady"] = True
            updated_count += 1
            time.sleep(0.2)

    save_json(PUBLISHED_FILE, pub_data)
    print(f"[OK] 리더 뷰(이미지·본문) 추출 완료: 총 {updated_count}건 업데이트")

def fetch_naver_news(query, client_id, client_secret, display=30, log_detail=False):
    encoded = urllib.parse.quote(query)
    url_hub = f"https://naveropenapi.apigw.ntruss.com/search/v1/news.json?query={encoded}&display={display}&sort=date"
    req_hub = urllib.request.Request(url_hub)
    req_hub.add_header("X-NCP-APIGW-API-KEY-ID", client_id)
    req_hub.add_header("X-NCP-APIGW-API-KEY", client_secret)
    try:
        with urllib.request.urlopen(req_hub, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8')).get('items', []), "NAVER_HUB"
    except urllib.error.HTTPError:
        url_dev = f"https://openapi.naver.com/v1/search/news.json?query={encoded}&display={display}&sort=date"
        req_dev = urllib.request.Request(url_dev)
        req_dev.add_header("X-Naver-Client-Id", client_id)
        req_dev.add_header("X-Naver-Client-Secret", client_secret)
        with urllib.request.urlopen(req_dev, timeout=10) as resp2:
            return json.loads(resp2.read().decode('utf-8')).get('items', []), "NAVER_DEV"

def fetch_google_rss_fallback(query, start_dt, end_dt):
    after_str = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    before_str = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    full_q = f'{query} after:{after_str} before:{before_str}'
    encoded = urllib.parse.quote(full_q)
    rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(rss_url, headers={"User-Agent": UA_HEADER["User-Agent"]})
    with urllib.request.urlopen(req, timeout=10) as resp:
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
            'customPress': press or '주요언론'
        })
    return items_out

def main():
    mode = os.environ.get("RUN_MODE", "scrape").strip()
    target = os.environ.get("TARGET_AFFILIATE", "all").strip()

    if mode == "enrich_published":
        enrich_published_articles(target)
        return

    client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    start_str = os.environ.get("START_DATE", "").strip()
    end_str = os.environ.get("END_DATE", "").strip()

    now_dt = datetime.now(KST)
    pool_data = load_json(POOL_FILE, {"updatedAt": "", "keywords": DEFAULT_KEYWORDS, "affiliates": {}})
    pub_data = load_json(PUBLISHED_FILE, {"history": {}, "published": {}})

    saved_kw = pool_data.get("keywords") or {}
    active_keywords = {}
    for k in DEFAULT_KEYWORDS:
        active_keywords[k] = flatten_keywords(saved_kw.get(k)) if k in saved_kw else DEFAULT_KEYWORDS[k]

    history_map = pub_data.get("history", {})
    affiliates_out = pool_data.get("affiliates", {})
    naver_auth_failed = False

    for aff_key, kw_list in active_keywords.items():
        if target != "all" and target != aff_key:
            continue

        history_set = set(history_map.get(aff_key, []))
        start_dt, end_dt, range_label = get_date_bounds(now_dt, start_str, end_str)
        collected = []
        seen_norms = set()
        used_source = "NAVER API"

        for idx, kw in enumerate(kw_list):
            items = []
            if client_id and client_secret and not naver_auth_failed:
                try:
                    items, src = fetch_naver_news(kw, client_id, client_secret, display=30, log_detail=(idx == 0))
                    used_source = src
                except Exception:
                    naver_auth_failed = True

            if not items and (naver_auth_failed or not client_id):
                try:
                    items = fetch_google_rss_fallback(kw, start_dt, end_dt)
                    used_source = "Google News RSS"
                except Exception as e2:
                    print(f"[WARN] {aff_key} - {kw} 백업 수집 실패: {e2}")
                    continue

            for item in items:
                title = clean_html(item.get('title', ''))
                orig_link = item.get('originallink') or item.get('link') or ''
                pub_raw = item.get('pubDate', '')

                if not title or not orig_link:
                    continue

                try:
                    pub_dt = parsedate_to_datetime(pub_raw).astimezone(KST)
                    if pub_dt < start_dt or pub_dt > end_dt:
                        continue
                    time_label = pub_dt.strftime('%Y.%m.%d %H:%M')
                    pub_iso = pub_dt.isoformat()
                    pub_ts = pub_dt.timestamp()
                except Exception:
                    time_label = now_dt.strftime('%Y.%m.%d %H:%M')
                    pub_iso = now_dt.isoformat()
                    pub_ts = now_dt.timestamp()

                norm = normalize_title(title)
                if not norm or norm in seen_norms:
                    continue
                seen_norms.add(norm)

                initial_cat = "ind"
                if kw_list and kw_list[0].lower() in title.lower():
                    initial_cat = "own"

                press_name = item.get('customPress') or extract_press(orig_link)

                collected.append({
                    "id": int(time.time() * 1000) + len(collected),
                    "category": initial_cat,
                    "press": press_name,
                    "title": title,
                    "url": orig_link,
                    "pubDateISO": pub_iso,
                    "time": time_label,
                    "pubTs": pub_ts,
                    "matchedKw": kw,
                    "duplicate": norm in history_set,
                    "selected": False
                })
            time.sleep(0.08)

        collected.sort(key=lambda x: -x['pubTs'])

        affiliates_out[aff_key] = {
            "scrapedAt": f"{now_dt.strftime('%Y-%m-%d %H:%M:%S KST')} ({used_source})",
            "dateRange": range_label,
            "count": len(collected),
            "articles": collected
        }
        print(f"[OK] {aff_key} ({range_label} / {used_source}): 총 {len(collected)}건 수집")

    pool_data["updatedAt"] = now_dt.strftime('%Y-%m-%d %H:%M:%S KST')
    pool_data["keywords"] = active_keywords
    pool_data["affiliates"] = affiliates_out

    save_json(POOL_FILE, pool_data)
    if not os.path.exists(PUBLISHED_FILE):
        save_json(PUBLISHED_FILE, pub_data)

if __name__ == '__main__':
    main()
