# 상상인그룹 뉴스 모니터링 – 적용 안내

## 1. 파일 반영
이 폴더의 **모든 파일**을 저장소 루트에 덮어쓰기로 올립니다. (숨김 폴더 `.github/workflows/` 포함)
- 삭제할 파일: 루트의 `naver_scrape.yml` (기존에는 이 사본에만 스케줄이 있어 동작하지 않았습니다. 이제 `.github/workflows/naver_scrape.yml` 하나로 통합)

## 2. 네이버 연동 확인 (가장 먼저)
1. 저장소 ▸ Settings ▸ Secrets and variables ▸ Actions 에 아래 두 개가 **이름 그대로** 있는지 확인
   - `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (값 앞뒤 공백 주의)
2. 네이버 클라우드 플랫폼(console.ncloud.com) ▸ Application Services ▸ **NAVER API HUB** ▸ Application 에 **검색(뉴스)** API가 등록되어 있는지, 그리고 그 Application의 **인증 정보**에서 Client ID/Secret 을 복사했는지 확인
   (네이버 개발자센터의 검색 API는 NAVER API HUB로 이관되어 예전 개발자센터 키는 더 이상 쓰이지 않습니다)
3. Actions ▸ *Daily News Scrape* ▸ Run workflow 로 1회 수동 실행
4. 관리자 ▸ [수집] 탭 ▸ **네이버 연동 진단**에서 결과 확인 (실패 원인이 문장으로 표시됩니다)

(선택) 실패 알림을 슬랙으로 받으려면 `SLACK_WEBHOOK_URL` Secret 추가. 설정하지 않아도 GitHub 실패 메일이 갑니다.

## 3. 관리자 비밀번호
- 처음 `admin.html` 접속 시 **비밀번호 설정 화면**이 나옵니다. (10자 이상 권장, 기존 비밀번호는 이미 공개되었으므로 사용 금지)
- 화면에 나오는 `ADMIN_PW_HASH: '…'` 값을 `assets/common.js` 에 붙여넣어 커밋하면 다른 기기에서도 같은 비밀번호로 접속됩니다.
- GitHub 토큰: **Fine-grained 토큰**을 이 저장소 한 곳에만, 권한 *Contents: Read and write* + *Actions: Read and write* 로 발급해 [설정] 탭에 등록

## 4. 자동 일정 (매일 오전 6시 30분, 한국시간)
GitHub가 매일 06:30경 자동으로 실행하고, 프로그램이 오늘 수집할지 판단합니다.

| 대상 | 수집하는 날 | 수집 기간 |
|---|---|---|
| 상상인 · 엠아이텍 · 시너지이노베이션 · 메디카코리아 | 영업일(월~금, 공휴일 제외) | 직전 영업일 00:00 ~ 당일 06:30 |
| 뉴로바이오젠 · 사회공헌 (위클리) | 그 주 마지막 영업일(보통 금요일) | 지난주 같은 요일 00:00 ~ 당일 06:30 |

- 예) 화요일: 월 00:00~화 06:30 / 월요일: 금 00:00~월 06:30 / 연휴 다음 날: 연휴 직전 영업일 00:00부터
- 주말·공휴일(대체공휴일 포함)·회사 휴무일은 건너뜁니다. 회사 휴무일은 관리자 ▸ 수집 탭(비밀번호 해제 후) 또는 `holidays.json` 에서 추가합니다.
- 이미 발행한 기사는 후보에서 자동 제외됩니다.
- 수동 수집은 관리자 ▸ 수집 탭에서 **메인 관리자 비밀번호**를 입력해야 실행됩니다. (네이버 검색 한도 보호)
GitHub 스케줄은 혼잡 시 수 분~수십 분 늦을 수 있습니다. 수집 종료 시각은 항상 당일 06:30로 고정이라 늦어져도 기간은 변하지 않습니다.

## 5. 데이터 구조
- `holidays.json` : 회사 휴무일 추가 / 근무일 지정
- `keywords.json` : 계열사별 자사/경쟁사/업계 키워드 (관리자 [키워드] 탭에서 수정)
- `scraped_pool.json` : 오늘 수집된 후보 기사 + 네이버 연동 진단
- `published_data.json` : 계열사별 최신 발행분
- `archive/` : 날짜별 발행 기록(최근 90일, 발행할 때마다 `.github/workflows/archive.yml` 이 자동 갱신), `index.json`(날짜 목록) · `search.json`(검색용) · `stats.json`(추이 통계)
- 색상 변경: `assets/common.css` 상단의 `--brand` 등 변수만 수정

## 6. 관리자 페이지 (담당자만 접속)
- **관리자 주소: https://ssi-pr.sioll.workers.dev/admin.html**
- 임직원 페이지(GitHub Pages)에는 관리자 페이지와 링크가 없습니다. 기존 주소의 `/admin.html` 은 404입니다.
  임직원 페이지는 `.github/workflows/pages.yml` 이 관리자·내부 파일을 뺀 채로 배포합니다. (Settings ▸ Pages ▸ Source = GitHub Actions)

### 접속 방법
1. 위 주소에 접속하면 **Cloudflare Access** 로그인 화면(`ssi-pr.cloudflareaccess.com`)이 나옵니다.
2. 허용된 이메일을 입력하면 6자리 코드가 메일로 옵니다(10분 유효). 입력하면 24시간 동안 로그인이 유지됩니다.
   - 네이버 메일은 코드 메일이 도착하지 않는 경우가 있어 Gmail·회사 메일을 권장합니다.
3. 이어서 기존 관리자 비밀번호 화면이 나옵니다(2차 잠금).
4. 처음 접속한 브라우저에서는 [설정] 탭에서 GitHub 토큰을 한 번 등록합니다.

### 구성 (Cloudflare)
- **사이트**: Workers & Pages ▸ `ssi-pr` (Worker, 정적 파일). GitHub 저장소 main 에 연결되어 있어 main 이 바뀌면 자동으로 다시 배포됩니다.
- **잠금**: Zero Trust ▸ Access ▸ Applications ▸ **PR 관리자 페이지**
  - 보호 주소: `ssi-pr.sioll.workers.dev`, 미리보기 주소 `*-ssi-pr.sioll.workers.dev`
  - 로그인 방식: One-time PIN(이메일 코드)
  - 정책 **PR팀 담당자**(Allow): 허용 이메일 목록

### 담당자 추가·삭제
Cloudflare ▸ Zero Trust ▸ Access ▸ Applications ▸ **PR 관리자 페이지** ▸ Policies ▸ **PR팀 담당자** ▸ Include 의 Emails 에 이메일을 추가하거나 지우고 저장합니다.
