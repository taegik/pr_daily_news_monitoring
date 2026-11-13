import os
import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
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
    return (text.replace('&quot;', '"').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>')
                .replace('&apos;', "'")).strip()

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

def fetch_naver_news(query, client_id, client_secret, display=30, log_detail=False):
    encoded = urllib.parse.quote(query)
    # 1순위: 네이버 클라우드 플랫폼 NAVER API HUB (search/v1/news.json)
    url_hub = f"https://naveropenapi.apigw.ntruss.com/search/v1/news.json?query={encoded}&display={display}&sort=date"
    req_hub = urllib.request.Request(url_hub)
    req_hub.add_header("X-NCP-APIGW-API-KEY-ID", client_id)
    req_hub.add_header("X-NCP-APIGW-API-KEY", client_secret)
    try:
        with urllib.request.urlopen(req_hub, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8')).get('items', []), "NAVER_HUB"
    except urllib.error.HTTPError as e1:
        err_body1 = ""
        try:
            err_body1 = e1.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        if log_detail:
            print(f"[DEBUG] NAVER API HUB 응답 ({e1.code}): {err_body1}")

        # 2순위: 일반 네이버 개발자센터 (openapi.naver.com)
        url_dev = f"https://openapi.naver.com/v1/search/news.json?query={encoded}&display={display}&sort=date"
        req_dev = urllib.request.Request(url_dev)
        req_dev.add_header("X-Naver-Client-Id", client_id)
        req_dev.add_header("X-Naver-Client-Secret", client_secret)
        try:
            with urllib.request.urlopen(req_dev, timeout=10) as resp2:
                return json.loads(resp2.read().decode('utf-8')).get('items', []), "NAVER_DEV"
        except urllib.error.HTTPError as e2:
            err_body2 = ""
            try:
                err_body2 = e2.read().decode('utf-8', errors='ignore')
            except Exception:
                pass
            if log_detail:
                print(f"[DEBUG] NAVER DEV 응답 ({e2.code}): {err_body2}")
            raise RuntimeError(f"Naver API 인증 실패 (HUB:{e1.code}, DEV:{e2.code})")

def fetch_google_rss_fallback(query, start_dt, end_dt):
    # 네이버 API 인증 실패 시 GitHub 서버에서 직접 Google News 한국어 RSS 수집 (CORS/방화벽 없음)
    after_str = (start_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    before_str = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    full_q = f'{query} after:{after_str} before:{before_str}'
    encoded = urllib.parse.quote(full_q)
    rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
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
    client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    target = os.environ.get("TARGET_AFFILIATE", "all").strip()
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
                except Exception as e:
                    if idx == 0:
                        print(f"[WARN] 네이버 API 인증 오류로 Google News RSS 백업 수집기로 자동 전환합니다: {e}")
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
