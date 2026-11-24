/* 상상인그룹 PR팀 뉴스 모니터링 - 공통 설정/유틸 (임직원 페이지 · 관리자 페이지 공용) */
(function (global) {
  'use strict';

  var PRM = {
    // ── 관리자 비밀번호 해시 ─────────────────────────────────────────────
    // 비어 있으면 admin.html 이 '비밀번호 설정' 화면을 보여줍니다.
    // 설정 화면에서 생성한 값을 아래에 붙여넣고 저장소에 올리면 활성화됩니다.
    ADMIN_PW_HASH: '488bd710ee6105885424ac435b4725567ea25ba888d2f106c6ebc1f1a4ad5bd7',
    ADMIN_PW_SALT: 'sangsangin-pr-news-v1',
    ADMIN_PW_ITER: 250000,

    // ── 계열사 ───────────────────────────────────────────────────────────
    AFFILIATES: {
      sangsangin:  { name: '상상인',          manager: '박슬기 과장', cycle: '매일 오전 8시~8시반', publishHour: 8,
                     quote: '위기는 곧 기회의 다른 이름이다.', author: '워런 버핏' },
      mitech:      { name: '엠아이텍',        manager: '박한솔 대리', cycle: '매일 오전 9시~9시반', publishHour: 9,
                     quote: '작은 디테일이 위대한 품질의 차이를 만든다.', author: '피터 드러커' },
      synergy:     { name: '시너지이노베이션', manager: '박한솔 대리', cycle: '매일 오전 9시~9시반', publishHour: 9,
                     quote: '시너지는 전체가 부분의 합보다 크다는 것을 증명한다.', author: '스티븐 코비' },
      medica:      { name: '메디카코리아',    manager: '김태기 과장', cycle: '매일 오전 9시~9시반', publishHour: 9,
                     quote: '나는 실패한 것이 아니다. 단지 효과가 없는 1만 가지 방법을 발견했을 뿐이다.', author: '토머스 에디슨' },
      neurobiogen: { name: '뉴로바이오젠',    manager: '김성목 대리', cycle: '주 1회 (매주 금요일)', publishHour: 9, weeklyDay: 5,
                     quote: '과학의 진보는 불가능해 보이는 질문을 던지는 데서 시작된다.', author: '알베르트 아인슈타인' }
    },
    CATS: {
      own:  { label: '자사',   desc: '자사 직접 보도' },
      comp: { label: '경쟁사', desc: '주요 경쟁사 동향' },
      ind:  { label: '업계',   desc: '정책·규제·산업 전반' }
    },
    DAYS: ['일', '월', '화', '수', '목', '금', '토'],
    TARGET_COUNT: 15,
    MIN_COUNT: 10
  };

  // ── 날짜 유틸 ('2026.11.13' <-> '2026-11-13') ─────────────────────────
  PRM.toIso = function (s) { return (s || '').trim().replace(/\./g, '-'); };
  PRM.toDot = function (s) { return (s || '').trim().replace(/-/g, '.'); };
  PRM.parseIso = function (iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  };
  PRM.dayLabel = function (iso) { var d = PRM.parseIso(iso); return d ? PRM.DAYS[d.getDay()] : ''; };
  PRM.fmtIso = function (d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  };
  PRM.todayIso = function () { return PRM.fmtIso(new Date()); };
  PRM.addDays = function (iso, n) { var d = PRM.parseIso(iso); d.setDate(d.getDate() + n); return PRM.fmtIso(d); };
  PRM.shortDate = function (iso) { var d = PRM.parseIso(iso); return d ? (d.getMonth() + 1) + '.' + d.getDate() : ''; };

  // ── 보안 유틸 ────────────────────────────────────────────────────────
  PRM.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  PRM.safeUrl = function (u) {
    try { var x = new URL(u, location.href); return /^https?:$/.test(x.protocol) ? x.href : '#'; } catch (e) { return '#'; }
  };
  PRM.shortHash = function (s) {
    var h = 5381; s = String(s || '');
    for (var i = 0; i < s.length; i++) { h = ((h << 5) + h + s.charCodeAt(i)) | 0; }
    return (h >>> 0).toString(36);
  };
  PRM.normTitle = function (t) {
    return String(t || '').replace(/\[[^\]]*\]/g, '').replace(/[^가-힣a-zA-Z0-9]/g, '').toLowerCase();
  };

  // 비밀번호 해시 (PBKDF2-SHA256) - 평문 비밀번호는 소스에 저장하지 않습니다.
  PRM.hashPassword = async function (pw) {
    if (!(global.crypto && global.crypto.subtle)) throw new Error('이 브라우저(또는 http 주소)에서는 해시를 만들 수 없습니다. https 주소에서 사용하세요.');
    var enc = new TextEncoder();
    var key = await crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveBits']);
    var bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: enc.encode(PRM.ADMIN_PW_SALT), iterations: PRM.ADMIN_PW_ITER }, key, 256);
    return Array.prototype.map.call(new Uint8Array(bits), function (b) { return b.toString(16).padStart(2, '0'); }).join('');
  };

  // ── 테마 (라이트/다크/자동) ───────────────────────────────────────────
  PRM.getThemePref = function () { try { return localStorage.getItem('pr_theme') || 'auto'; } catch (e) { return 'auto'; } };
  PRM.applyTheme = function (pref) {
    var dark = pref === 'dark' || (pref === 'auto' && global.matchMedia && global.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#0D171B' : '#FFFFFF');
  };
  PRM.setThemePref = function (pref) {
    try { localStorage.setItem('pr_theme', pref); } catch (e) {}
    PRM.applyTheme(pref);
  };
  PRM.applyTheme(PRM.getThemePref());
  if (global.matchMedia) {
    var mq = global.matchMedia('(prefers-color-scheme: dark)');
    var onChange = function () { if (PRM.getThemePref() === 'auto') PRM.applyTheme('auto'); };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
  }

  // ── 토스트 ───────────────────────────────────────────────────────────
  PRM.toast = function (msg, ms) {
    var t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(PRM._tt);
    PRM._tt = setTimeout(function () { t.classList.remove('show'); }, ms || 2600);
  };

  PRM.copyText = async function (text) {
    if (navigator.clipboard && global.isSecureContext) {
      try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
    }
    try {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', '');
      ta.style.cssText = 'position:fixed;top:0;left:0;width:2em;height:2em;opacity:0;font-size:16px';
      document.body.appendChild(ta); ta.focus(); ta.select(); ta.setSelectionRange(0, ta.value.length);
      var ok = document.execCommand('copy'); document.body.removeChild(ta);
      return ok;
    } catch (e) { return false; }
  };

  global.PRM = PRM;
})(window);
