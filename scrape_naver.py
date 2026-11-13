import os
import re
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))
POOL_FILE = 'scraped_pool.json'
PUBLISHED_FILE = 'published_data.json'

AFFILIATE_KEYWORDS = {
  "sangsangin": {
    "own": [
      "유준원",
      "상상인",
      "상상인증권",
      "상상인선박기계",
      "시너지이노베이션",
      "메디카코리아",
      "엠아이텍",
      "노비스바이오",
      "프로톡스",
      "에스앤지바이오텍",
      "바스노바"
    ],
    "comp": [
      "카카오뱅크",
      "카카오증권",
      "대신증권",
      "한화투자증권",
      "유안타증권",
      "교보증권",
      "현대차증권",
      "하이투자증권",
      "DB 금융투자",
      "IBK 투자증권",
      "다올투자증권",
      "유진투자증권",
      "이베스트투자증권",
      "부국증권",
      "SK 증권"
    ],
    "ind": [
      "리그테이블",
      "제2금융",
      "중소형증권",
      "금융당국",
      "금감원",
      "금융감독원",
      "금융위",
      "한국은행",
      "한국거래소",
      "PF",
      "IB",
      "투자은행",
      "MTS",
      "ELS",
      "IPO",
      "ECM"
    ]
  },
  "mitech": {
    "own": [
      "엠아이텍",
      "M.I.TECH",
      "MITECH",
      "에스앤지바이오텍",
      "S&G 바이오텍",
      "S&G BIOTEC",
      "바스노바"
    ],
    "comp": [
      "보스톤사이언티",
      "Boston Scientific",
      "쿡메디칼",
      "Cook Medical",
      "태웅메디칼",
      "올림푸스",
      "펜탁스 메디칼",
      "후지필름",
      "파인메딕스",
      "스텐트",
      "스탠트",
      "내시경장비",
      "초음파장비",
      "의료기기",
      "담도"
    ],
    "ind": [
      "식약처",
      "식품의약품안전처",
      "보건복지부",
      "의약품안전나라",
      "의료기기안심책방",
      "한국의료기기안전정보원",
      "한국의료기기산업협회",
      "한국제약바이오협회"
    ]
  },
  "synergy": {
    "own": [
      "시너지이노베이션"
    ],
    "comp": [
      "기산바이오",
      "고마바이오텍",
      "머크",
      "Merck",
      "써모피셔사이언티픽",
      "아미코젠",
      "아지노모도제넥신 셀리스트",
      "엑셀세라퓨틱스",
      "배지",
      "미생물배양",
      "세포배양"
    ],
    "ind": [
      "의료기기",
      "식약처",
      "보건복지부",
      "한국의료기기산업협회",
      "한국의료기기협동조합"
    ]
  },
  "medica": {
    "own": [
      "메디카코리아",
      "Medica Korea"
    ],
    "comp": [
      "동국제약",
      "종근당",
      "대웅제약",
      "동아제약",
      "유한양행"
    ],
    "ind": [
      "개량신약",
      "IMD",
      "약가 인하",
      "제네릭",
      "한국제약바이오협회",
      "식품의약품안전처",
      "의약품안전나라",
      "한국제약협동조합",
      "보건복지부"
    ]
  },
  "neurobiogen": {
    "own": [
      "뉴로바이오젠",
      "neurobiogen",
      "KDS2010",
      "티솔라질린"
    ],
    "comp": [
      "사이렉스",
      "사일렉스",
      "비만 치료제",
      "치매 치료제",
      "알츠하이머",
      "비만약",
      "치매약"
    ],
    "ind": [
      "식약처",
      "식품의약품안전처",
      "보건복지부",
      "의약품안전나라",
      "한국제약바이오협회"
    ]
  }
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

def get_window_seconds(affiliate_key, now_dt):
    if affiliate_key == 'neurobiogen':
        return 7 * 24 * 3600  # 주 1회 (금요일)
    if now_dt.weekday() == 0:
        return 78 * 3600      # 월요일: 금·토·일 주말 포함
    return 30 * 3600          # 평일: 전일~당일 오전

def fetch_naver_news(query, client_id, client_secret, display=25):
    encoded = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={encoded}&display={display}&sort=date"
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", client_id)
    req.add_header("X-Naver-Client-Secret", client_secret)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8')).get('items', [])

def main():
    client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    target = os.environ.get("TARGET_AFFILIATE", "all").strip()

    if not client_id or not client_secret:
        raise RuntimeError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 시크릿이 설정되지 않았습니다.")

    now_dt = datetime.now(KST)
    pool_data = load_json(POOL_FILE, {"updatedAt": "", "keywords": AFFILIATE_KEYWORDS, "affiliates": {}})
    pub_data = load_json(PUBLISHED_FILE, {"history": {}, "published": {}})

    # 관리자가 웹에서 저장한 최신 키워드가 있으면 우선 사용
    active_keywords = pool_data.get("keywords") or AFFILIATE_KEYWORDS
    for k in AFFILIATE_KEYWORDS:
        if k not in active_keywords:
            active_keywords[k] = AFFILIATE_KEYWORDS[k]

    history_map = pub_data.get("history", {})
    affiliates_out = pool_data.get("affiliates", {})

    for aff_key, kw_map in active_keywords.items():
        if target != "all" and target != aff_key:
            continue

        history_set = set(history_map.get(aff_key, []))
        max_age_sec = get_window_seconds(aff_key, now_dt)
        collected = []
        seen_norms = set()

        for cat_key in ['own', 'comp', 'ind']:
            kw_list = [k.strip() for k in kw_map.get(cat_key, []) if k.strip()]
            for kw in kw_list:
                try:
                    items = fetch_naver_news(kw, client_id, client_secret, display=20)
                except Exception as e:
                    print(f"[WARN] {aff_key} - {kw} 호출 실패: {e}")
                    continue

                for item in items:
                    title = clean_html(item.get('title', ''))
                    orig_link = item.get('originallink') or item.get('link') or ''
                    pub_raw = item.get('pubDate', '')

                    if not title or not orig_link:
                        continue

                    try:
                        pub_dt = parsedate_to_datetime(pub_raw).astimezone(KST)
                        age_sec = (now_dt - pub_dt).total_seconds()
                        if age_sec > max_age_sec or age_sec < -3600:
                            continue
                        time_label = pub_dt.strftime('%m.%d %H:%M')
                        pub_ts = pub_dt.timestamp()
                    except Exception:
                        time_label = "최근"
                        pub_ts = now_dt.timestamp()
                        age_sec = 3600

                    norm = normalize_title(title)
                    if not norm or norm in seen_norms:
                        continue
                    seen_norms.add(norm)

                    lower_title = title.lower()
                    final_cat = cat_key
                    hit_kw = kw
                    for own_k in kw_map.get('own', []):
                        if own_k.lower() in lower_title:
                            final_cat = 'own'
                            hit_kw = own_k
                            break

                    hours_ago = max(0, age_sec / 3600.0)
                    recency_bonus = max(0, round(20 - hours_ago * 0.5))
                    cat_bonus = 30 if final_cat == 'own' else (15 if final_cat == 'comp' else 5)
                    score = min(99, 65 + cat_bonus + recency_bonus)

                    collected.append({
                        "id": int(time.time() * 1000) + len(collected),
                        "category": final_cat,
                        "press": extract_press(orig_link),
                        "title": title,
                        "url": orig_link,
                        "time": time_label,
                        "pubTs": pub_ts,
                        "score": score,
                        "matchedKw": hit_kw,
                        "duplicate": norm in history_set,
                        "selected": False
                    })
                time.sleep(0.08)

        prio = {'own': 1, 'comp': 2, 'ind': 3}
        collected.sort(key=lambda x: (prio[x['category']], -x['score'], -x['pubTs']))

        picked = 0
        for item in collected:
            if not item['duplicate'] and picked < 15:
                item['selected'] = True
                picked += 1

        affiliates_out[aff_key] = {
            "scrapedAt": now_dt.strftime('%Y-%m-%d %H:%M:%S KST'),
            "count": len(collected),
            "picked": picked,
            "articles": collected
        }
        print(f"[OK] {aff_key}: 총 {len(collected)}건 수집, {picked}건 자동 선정")

    pool_data["updatedAt"] = now_dt.strftime('%Y-%m-%d %H:%M:%S KST')
    pool_data["keywords"] = active_keywords
    pool_data["affiliates"] = affiliates_out

    save_json(POOL_FILE, pool_data)
    if not os.path.exists(PUBLISHED_FILE):
        save_json(PUBLISHED_FILE, pub_data)

if __name__ == '__main__':
    main()
