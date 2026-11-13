import os
import re
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='.')

KST = timezone(timedelta(hours=9))
CONFIG_FILE = 'naver_api_config.json'
HISTORY_FILE = 'published_history.json'

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

# 언론사 도메인 -> 한글 매체명 매핑
DOMAIN_PRESS_MAP = {
    'hankyung.com': '한국경제',
    'mk.co.kr': '매일경제',
    'sedaily.com': '서울경제',
    'fnnews.com': '파이낸셜뉴스',
    'edaily.co.kr': '이데일리',
    'mt.co.kr': '머니투데이',
    'asiae.co.kr': '아시아경제',
    'heraldcorp.com': '헤럴드경제',
    'dt.co.kr': '디지털타임스',
    'etnews.com': '전자신문',
    'inews24.com': '아이뉴스24',
    'chosun.com': '조선일보',
    'joongang.co.kr': '중앙일보',
    'donga.com': '동아일보',
    'yna.co.kr': '연합뉴스',
    'newsis.com': '뉴시스',
    'news1.kr': '뉴스1',
    'einfomax.co.kr': '연합인포맥스',
    'dailypharm.com': '데일리팜',
    'medipana.com': '메디파나뉴스',
    'newsmp.com': '의약뉴스',
    'bosa.co.kr': '의학신문',
    'kpanews.co.kr': '약사공론',
    'yakup.com': '약업신문',
    'hitnews.co.kr': '히트뉴스',
    'biospectator.com': '바이오스펙테이터',
    'docdocdoc.co.kr': '청년의사',
    'dailymedi.com': '데일리메디',
    'medicaltimes.com': '메디컬타임즈',
    'rapportian.com': '라포르시안',
    'bokuennews.com': '보건뉴스',
    'skyedaily.com': '스카이데일리',
    'ceoscoredaily.com': 'CEO스코어데일리',
    'sisajournal-e.com': '시사저널e',
    'asiatime.co.kr': '아시아타임즈',
    'tf.co.kr': '더팩트',
    'm-i.kr': '매일일보'
}

def load_json_file(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json_file(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clean_html(raw):
    text = re.sub(r'<[^>]+>', '', raw or '')
    text = (text.replace('&quot;', '"').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>')
                .replace('&apos;', "'"))
    return text.strip()

def normalize_title(title):
    t = re.sub(r'\[[^\]]*\]', '', title or '')
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', t).lower()

def extract_press_name(url):
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        for domain, name in DOMAIN_PRESS_MAP.items():
            if domain in host:
                return name
        parts = host.replace('www.', '').split('.')
        return parts[0] if parts else '주요언론'
    except Exception:
        return '주요언론'

def get_window_seconds(affiliate_key):
    now = datetime.now(KST)
    if affiliate_key == 'neurobiogen':
        return 7 * 24 * 3600  # 주 1회 (금요일)
    if now.weekday() == 0:
        return 78 * 3600      # 월요일: 금·토·일 주말 포함
    return 30 * 3600          # 평일: 전일~당일 오전

def fetch_naver_news_api(query, client_id, client_secret, display=25):
    encoded = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={encoded}&display={display}&sort=date"
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", client_id)
    req.add_header("X-Naver-Client-Secret", client_secret)
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = resp.read().decode('utf-8')
        return json.loads(body).get('items', [])

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return send_from_directory('.', 'admin.html')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    cfg = load_json_file(CONFIG_FILE, {
        "clientId": os.environ.get("NAVER_CLIENT_ID", ""),
        "clientSecret": os.environ.get("NAVER_CLIENT_SECRET", ""),
        "keywords": AFFILIATE_KEYWORDS
    })
    if request.method == 'POST':
        payload = request.json or {}
        if 'clientId' in payload:
            cfg['clientId'] = payload['clientId'].strip()
        if 'clientSecret' in payload:
            cfg['clientSecret'] = payload['clientSecret'].strip()
        if 'keywords' in payload:
            cfg['keywords'] = payload['keywords']
        save_json_file(CONFIG_FILE, cfg)
        return jsonify({"status": "ok", "hasKey": bool(cfg['clientId'] and cfg['clientSecret'])})

    return jsonify({
        "clientId": cfg.get('clientId', ''),
        "hasKey": bool(cfg.get('clientId') and cfg.get('clientSecret')),
        "keywords": cfg.get('keywords', AFFILIATE_KEYWORDS)
    })

@app.route('/api/scrape', methods=['POST'])
def scrape_news():
    payload = request.json or {}
    affiliate = payload.get('affiliate', 'medica')
    cfg = load_json_file(CONFIG_FILE, {
        "clientId": os.environ.get("NAVER_CLIENT_ID", ""),
        "clientSecret": os.environ.get("NAVER_CLIENT_SECRET", ""),
        "keywords": AFFILIATE_KEYWORDS
    })

    client_id = (payload.get('clientId') or cfg.get('clientId') or '').strip()
    client_secret = (payload.get('clientSecret') or cfg.get('clientSecret') or '').strip()

    if not client_id or not client_secret:
        return jsonify({"status": "error", "message": "네이버 API Client ID와 Client Secret을 먼저 설정해주세요."}), 400

    kw_map = payload.get('keywords') or cfg.get('keywords', {}).get(affiliate) or AFFILIATE_KEYWORDS.get(affiliate, {})
    history_all = load_json_file(HISTORY_FILE, {})
    history_set = set(history_all.get(affiliate, []))

    now_dt = datetime.now(KST)
    max_age_sec = get_window_seconds(affiliate)
    collected = []
    seen_norms = set()

    # 카테고리별 키워드 순회 (자사 -> 경쟁사 -> 업계)
    for cat_key in ['own', 'comp', 'ind']:
        kw_list = [k.strip() for k in kw_map.get(cat_key, []) if k.strip()]
        for kw in kw_list:
            try:
                items = fetch_naver_news_api(kw, client_id, client_secret, display=20)
            except Exception as e:
                return jsonify({"status": "error", "message": f"네이버 API 호출 오류: {str(e)}"}), 502

            for item in items:
                title = clean_html(item.get('title', ''))
                orig_link = item.get('originallink') or item.get('link') or ''
                pub_raw = item.get('pubDate', '')

                if not title or not orig_link:
                    continue

                # 발행 시간 필터링
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

                # 자사명 포함 여부 최우선 재판정
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
                    "press": extract_press_name(orig_link),
                    "title": title,
                    "url": orig_link,
                    "time": time_label,
                    "pubTs": pub_ts,
                    "score": score,
                    "matchedKw": hit_kw,
                    "duplicate": norm in history_set,
                    "selected": False
                })
            time.sleep(0.06)  # 네이버 API 초당 호출 제한(10회/초) 준수

    # 우선순위(자사 -> 경쟁사 -> 업계) 및 중요도순 정렬
    prio = {'own': 1, 'comp': 2, 'ind': 3}
    collected.sort(key=lambda x: (prio[x['category']], -x['score'], -x['pubTs']))

    picked = 0
    for item in collected:
        if not item['duplicate'] and picked < 15:
            item['selected'] = True
            picked += 1

    return jsonify({
        "status": "ok",
        "count": len(collected),
        "picked": picked,
        "articles": collected
    })

@app.route('/api/publish', methods=['POST'])
def publish_articles():
    payload = request.json or {}
    affiliate = payload.get('affiliate', 'medica')
    articles = payload.get('articles', [])

    # 1. 발행 데이터 JSON 저장 (임직원 페이지에서 실시간 조회 가능)
    pub_file = f"published_{affiliate}.json"
    save_json_file(pub_file, payload)

    # 2. 과거 중복 차단 이력 누적 저장
    history_all = load_json_file(HISTORY_FILE, {})
    existing = set(history_all.get(affiliate, []))
    for a in articles:
        n = normalize_title(a.get('title', ''))
        if n:
            existing.add(n)
    history_all[affiliate] = list(existing)[-500:]
    save_json_file(HISTORY_FILE, history_all)

    return jsonify({"status": "ok", "saved": len(articles)})

@app.route('/api/published/<affiliate>', methods=['GET'])
def get_published(affiliate):
    pub_file = f"published_{affiliate}.json"
    data = load_json_file(pub_file, None)
    if data:
        return jsonify({"status": "ok", "data": data})
    return jsonify({"status": "empty"})

if __name__ == '__main__':
    print("=== 상상인그룹 PR팀 뉴스모니터링 서버 가동 (http://localhost:5000) ===")
    print(" - 임직원 페이지: http://localhost:5000/")
    print(" - 관리자 페이지: http://localhost:5000/admin")
    app.run(host='0.0.0.0', port=5000, debug=False)
