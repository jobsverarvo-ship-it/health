/* 건강한통 공통 스크립트: 서버 연결, 로그인 상태, 글자 크기, 소리로 듣기, 가족에게 보내기.
   회원 정보와 저장한 정보는 서버(server 폴더)에 있고, 이 기기에는 글자 크기 같은 화면 설정만 남긴다. */
(function () {
  'use strict';
  var root = document.documentElement;
  var KEY = { size: 'haruon-size', hint: 'haruon-hint', in: 'ght-in' };

  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function write(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }

  var CATS = {
    medicine_food: '약과 음식 궁합',
    supplement: '영양제 제대로 먹기',
    body_signal: '몸이 보내는 신호',
    safety: '생활 속 사고 예방',
    benefit: '나라에서 주는 혜택',
    brain_sense: '뇌와 감각 건강'
  };
  var WEEKDAYS = '일월화수목금토';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtDate(d) { return (d.getMonth() + 1) + '월 ' + d.getDate() + '일 ' + WEEKDAYS[d.getDay()] + '요일'; }

  /* ---- 서버와 주고받기 ----
     실패하면 { status, code, message } 를 담은 오류를 돌려준다.
     code 'offline' = 인터넷이 끊김,  'no_server' = 서버 없이 파일만 올라간 곳(예: GitHub Pages) */
  var NO_SERVER = '지금 보고 계신 곳은 화면만 보여 주는 미리보기라 가입과 로그인을 할 수 없어요.';
  function apiError(status, code, message, extra) {
    var e = new Error(message);
    e.status = status; e.code = code; e.data = extra || {};
    return e;
  }
  function api(method, path, body) {
    var opts = { method: method, credentials: 'same-origin', headers: { 'X-Requested-With': 'ght', 'Accept': 'application/json' } };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch('api/' + path, opts).then(function (res) {
      var json = (res.headers.get('content-type') || '').indexOf('application/json') >= 0;
      if (!json) throw apiError(res.status, 'no_server', NO_SERVER);
      return res.json().then(function (data) {
        if (res.ok) return data;
        var d = data && data.detail;
        if (d && d.code) throw apiError(res.status, d.code, d.message, d);
        if (res.status === 422) throw apiError(422, 'invalid', '적어 주신 내용을 다시 확인해 주세요.');
        throw apiError(res.status, 'server', '잠시 문제가 생겼어요. 조금 뒤에 다시 해 주세요.');
      });
    }, function () {
      throw apiError(0, 'offline', '서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 해 주세요.');
    });
  }

  /* ---- 알림 메시지 ---- */
  var toastEl, toastTimer;
  function toast(msg) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'toast';
      toastEl.setAttribute('role', 'status');
      toastEl.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 3200);
  }

  /* ---- 소리로 듣기 (브라우저 음성 읽기) ---- */
  var playingBtn = null;
  function setPlaying(btn, on) {
    if (!btn) return;
    btn.classList.toggle('is-playing', on);
    var label = btn.querySelector('[data-label]');
    if (label) label.textContent = on ? '멈추기' : '소리로 듣기';
  }
  function speak(text, btn) {
    if (!('speechSynthesis' in window)) { toast('이 기기에서는 소리로 듣기를 쓸 수 없어요.'); return; }
    var synth = window.speechSynthesis;
    if (synth.speaking) {
      synth.cancel();
      var was = playingBtn; setPlaying(playingBtn, false); playingBtn = null;
      if (was === btn) return;
    }
    var u = new SpeechSynthesisUtterance(text);
    u.lang = 'ko-KR';
    u.rate = 0.9;
    var voices = synth.getVoices ? synth.getVoices() : [];
    for (var i = 0; i < voices.length; i++) { if (voices[i].lang && voices[i].lang.indexOf('ko') === 0) { u.voice = voices[i]; break; } }
    u.onend = u.onerror = function () { setPlaying(btn, false); if (playingBtn === btn) playingBtn = null; };
    playingBtn = btn;
    setPlaying(btn, true);
    synth.speak(u);
  }

  /* ---- 가족에게 보내기 ---- */
  function share(title, text) {
    var full = title + '\n' + text + '\n\n건강한통에서 받은 건강 정보예요.';
    if (navigator.share) {
      navigator.share({ title: title, text: full }).catch(function () {});
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(full).then(function () {
        toast('글을 복사했어요. 카카오톡 대화방에 붙여 넣어 보내 주세요.');
      }, function () { toast('복사하지 못했어요. 글을 길게 눌러 직접 복사해 주세요.'); });
    } else {
      toast('글을 길게 눌러 복사한 뒤 보내 주세요.');
    }
  }

  /* ---- 로그인 상태 ----
     me() 는 서버에 물어본 결과를 한 번만 받아 와 같이 쓴다. 로그인 안 했으면 null.
     'ght-in' 은 화면 깜빡임을 줄이려는 표시일 뿐이고, 진짜 로그인 여부는 늘 서버가 정한다. */
  var mePromise = null;
  function me(force) {
    if (!mePromise || force) {
      mePromise = api('GET', 'session').then(function (d) { return d.user; })
        .then(function (u) { renderAuth(u); return u; }, function (e) { renderAuth(null); throw e; });
    }
    return mePromise;
  }
  var configPromise = null;
  function config() {
    if (!configPromise) configPromise = api('GET', 'config');
    return configPromise;
  }
  function setUser(u) { mePromise = Promise.resolve(u); renderAuth(u); }

  function renderAuth(u) {
    write(KEY.in, u ? '1' : null);
    Array.prototype.forEach.call(document.querySelectorAll('[data-when="in"]'), function (el) { el.hidden = !u; });
    Array.prototype.forEach.call(document.querySelectorAll('[data-when="out"]'), function (el) { el.hidden = !!u; });
    Array.prototype.forEach.call(document.querySelectorAll('[data-user-name]'), function (el) { el.textContent = u ? u.name : ''; });
  }

  function logout() {
    return api('POST', 'auth/logout').catch(function () {}).then(function () { setUser(null); });
  }

  /* 로그인 · 가입으로 보내는 주소 */
  function kakaoUrl(next) { return 'api/auth/kakao/start?next=' + encodeURIComponent(next || 'my.html'); }
  function phoneUrl(next) { return 'start.html?method=phone&next=' + encodeURIComponent(next || 'my.html'); }

  /* 서버를 쓸 수 없을 때 보여 줄 안내 */
  function problemPanel(e) {
    var noServer = e && e.code === 'no_server';
    return '<section class="panel" style="text-align:center">' +
      '<h1 class="page-title">' + (noServer ? '지금은 미리보기 화면이에요' : '잠시 연결이 안 돼요') + '</h1>' +
      '<p class="page-sub">' + esc(e ? e.message : '') + '</p>' +
      (noServer ? '' : '<button type="button" class="btn btn-primary" onclick="location.reload()">다시 해 보기</button>') +
      '<p style="margin-top:1.2rem"><a class="btn-text" href="index.html">처음 화면으로</a></p></section>';
  }

  /* ---- 글자 크기: '글자 크기' 버튼을 누르면 보통 / 크게 / 더 크게 를 고르는 창이 열린다 ---- */
  var sizeToggle = document.getElementById('size-toggle');
  var sizeMenu = document.getElementById('size-menu');
  var sizeBtns = Array.prototype.slice.call(document.querySelectorAll('[data-size-btn]'));
  var SIZE_NAME = { md: '보통', lg: '크게', xl: '더 크게' };
  function setSize(s) {
    if (s === 'md') root.removeAttribute('data-size'); else root.setAttribute('data-size', s);
    sizeBtns.forEach(function (b) { b.setAttribute('aria-checked', String(b.getAttribute('data-size-btn') === s)); });
    if (sizeToggle) sizeToggle.setAttribute('aria-label', '글자 크기 바꾸기, 지금은 ' + SIZE_NAME[s]);
    write(KEY.size, s);
  }
  var size = read(KEY.size) || 'md';
  if (['md', 'lg', 'xl'].indexOf(size) < 0) size = 'md';
  setSize(size);

  var hint = document.getElementById('size-hint');
  function hideHint() { if (hint) hint.hidden = true; write(KEY.hint, 'off'); }
  if (hint && (read(KEY.hint) === 'off' || size !== 'md')) hint.hidden = true;
  var hintClose = document.getElementById('size-hint-close');
  if (hintClose) hintClose.addEventListener('click', hideHint);

  function menuOpen() { return sizeMenu && !sizeMenu.hidden; }
  function openMenu() {
    sizeMenu.hidden = false;
    sizeToggle.setAttribute('aria-expanded', 'true');
    hideHint();
    var on = sizeMenu.querySelector('[aria-checked="true"]') || sizeBtns[0];
    if (on) on.focus();
  }
  function closeMenu(focusBack) {
    if (!menuOpen()) return;
    sizeMenu.hidden = true;
    sizeToggle.setAttribute('aria-expanded', 'false');
    if (focusBack) sizeToggle.focus();
  }
  if (sizeToggle && sizeMenu) {
    sizeToggle.addEventListener('click', function () { if (menuOpen()) closeMenu(false); else openMenu(); });
    sizeBtns.forEach(function (b, i) {
      b.addEventListener('click', function () { setSize(b.getAttribute('data-size-btn')); closeMenu(true); });
      b.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          sizeBtns[(i + (e.key === 'ArrowDown' ? 1 : sizeBtns.length - 1)) % sizeBtns.length].focus();
        }
      });
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menuOpen()) closeMenu(true); });
    document.addEventListener('click', function (e) {
      if (menuOpen() && !sizeMenu.contains(e.target) && !sizeToggle.contains(e.target)) closeMenu(false);
    });
  }

  /* ---- 로그아웃 버튼 ---- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target.closest('[data-logout]') : null;
    if (!t) return;
    e.preventDefault();
    t.disabled = true;
    logout().then(function () {
      toast('로그아웃했어요.');
      setTimeout(function () { location.href = 'index.html'; }, 700);
    });
  });

  /* ---- 움직임: 화면에 들어올 때 한 번 나타나기 ----
     동작 줄이기를 켠 기기, 오래된 브라우저에서는 아무것도 숨기지 않는다. */
  var canMotion = 'IntersectionObserver' in window &&
    !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  if (canMotion) root.classList.add('js-motion');
  var io = canMotion ? new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      var el = en.target;
      io.unobserve(el);
      el.classList.add('in');
      if (el.classList.contains('reveal')) {
        var d = parseFloat(el.style.getPropertyValue('--d')) || 0;
        // 나타난 뒤에는 원래 효과(마우스를 올렸을 때 등)가 그대로 동작하도록 정리
        setTimeout(function () { el.classList.remove('reveal'); el.style.removeProperty('--d'); }, 900 + d * 1000);
      }
    });
  }, { rootMargin: '0px 0px -6% 0px', threshold: 0.12 }) : null;
  // reveal(선택자): 서서히 떠오르며 나타남. 같은 부모 안에서는 차례로.  watch(선택자): 보일 때 'in' 만 붙임
  function reveal(selector) {
    if (!io) return;
    Array.prototype.forEach.call(document.querySelectorAll(selector), function (el) {
      var p = el.parentNode;
      p.__ghtN = (p.__ghtN || 0) + 1;
      el.classList.add('reveal');
      el.style.setProperty('--d', Math.min((p.__ghtN - 1) * 0.09, 0.45) + 's');
      io.observe(el);
    });
  }
  function watch(selector) {
    if (!io) return;
    Array.prototype.forEach.call(document.querySelectorAll(selector), function (el) { io.observe(el); });
  }

  /* ---- 스크롤하면 머리글에 옅은 그림자 ---- */
  var header = document.querySelector('.site-header');
  if (header) {
    var onScroll = function () { header.classList.toggle('scrolled', window.scrollY > 8); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // 지난번 상태로 먼저 그려 두고, 서버 답이 오면 바로잡는다
  renderAuth(read(KEY.in) === '1' ? { name: '' } : null);
  me().catch(function () {});

  window.GHT = {
    CATS: CATS, esc: esc, fmtDate: fmtDate, toast: toast, speak: speak, share: share,
    api: api, me: me, config: config, setUser: setUser, logout: logout,
    kakaoUrl: kakaoUrl, phoneUrl: phoneUrl, problemPanel: problemPanel, reveal: reveal, watch: watch, motion: canMotion,
    fmtPhone: function (v) {
      var d = String(v || '').replace(/\D/g, '').slice(0, 11);
      if (d.length < 4) return d;
      if (d.length < 8) return d.slice(0, 3) + '-' + d.slice(3);
      return d.slice(0, 3) + '-' + d.slice(3, d.length - 4) + '-' + d.slice(-4);
    },
    validPhone: function (v) { return /^01[016789]\d{7,8}$/.test(String(v || '').replace(/\D/g, '')); },
    param: function (name) { try { return new URLSearchParams(location.search).get(name); } catch (e) { return null; } },
    parseDate: function (s) { var p = String(s).split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  };
})();
