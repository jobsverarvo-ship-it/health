/* 가입 · 로그인 (한 화면에 질문 하나)
   휴대폰:  번호 → 인증번호 → (처음이면) 이름 → 관심 건강 → 받는 시간 → 동의 → 완료
   카카오:  카카오 로그인 창 → 서버가 이 화면으로 돌려보냄(?step=profile) → (처음이면) 이름 → 관심 건강 → 받는 시간 → 동의 → 완료
   이미 가입한 분은 같은 방법으로 들어오면 그 자리에서 로그인된다. 판단은 모두 서버가 한다. */
(function () {
  'use strict';
  var G = window.GHT;
  var flow = document.getElementById('flow');
  var devNote = document.getElementById('dev-note');
  var nextPage = G.param('next');
  if (!nextPage || !/^(index|my|membership)\.html(#[a-z]+)?$/.test(nextPage)) nextPage = 'my.html';
  var goLabel = nextPage.indexOf('membership') === 0 ? '멤버십 신청 이어서 하기' : '내 건강정보함 보기';

  var INTERESTS = ['혈압', '당뇨', '관절·뼈', '심장', '눈', '귀', '기억력', '수면', '소화'];
  var CHECK = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var DONE = '<div class="done-icon" aria-hidden="true"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></div>';
  var KAKAO = '<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4C7 4 3 7.2 3 11.1c0 2.5 1.6 4.6 4.1 5.9L6.3 20.5l4-2.6c.6.1 1.1.1 1.7.1 5 0 9-3.2 9-7S17 4 12 4z" fill="currentColor"/></svg>';
  var PHONE = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="6.5" y="2.5" width="11" height="19" rx="2.5"/><path d="M10.5 18.5h3" stroke-linecap="round"/></svg>';

  var ERRORS = {
    kakao_cancel: '카카오 로그인을 취소하셨어요. 다시 하시려면 아래 버튼을 눌러 주세요.',
    kakao_state: '로그인 시간이 지났어요. 한 번 더 눌러 주세요.',
    kakao_failed: '카카오에서 정보를 받아 오지 못했어요. 잠시 뒤에 다시 해 주세요.',
    kakao_unavailable: '지금은 카카오 로그인을 쓸 수 없어요. 휴대폰 번호로 시작해 주세요.'
  };

  var cfg = { kakao: true, kakao_practice: false, sms_console: false };
  var state = { method: null, verified: false, name: '', phone: '', interests: [], channel: 'kakao', time: '8', user: null };
  var steps = [];
  var idx = 0;
  var notice = '';   // 처음 화면 위쪽에 띄울 안내

  function begin(method) {
    state.method = method;
    state.channel = method === 'kakao' ? 'kakao' : 'sms';
    steps = ['phone', 'code', 'name', 'interests', 'delivery', 'agree', 'done'];
    idx = 0;
    render();
  }
  function beginProfile(p) {
    state.method = p.method;
    state.verified = true;
    state.phone = p.phone || '';
    state.name = state.name || p.name_hint || '';
    state.channel = p.method === 'kakao' ? 'kakao' : 'sms';
    steps = ['name', 'interests', 'delivery', 'agree', 'done'];
    idx = 0;
    render();
  }
  function restart(msg) {
    state = { method: null, verified: false, name: '', phone: '', interests: [], channel: 'kakao', time: '8', user: null };
    notice = msg || '';
    render('method');
  }

  function progress() {
    var total = steps.length - 1; // 완료 화면 제외
    var n = Math.min(idx + 1, total);
    return '<div class="progress" aria-label="' + total + '단계 가운데 ' + n + '단계">' +
      '<div class="progress-bar"><span style="width:' + Math.round(n / total * 100) + '%"></span></div>' +
      '<span class="progress-text">' + n + ' / ' + total + '</span></div>';
  }

  function nav(nextLabel, noBack) {
    return '<div class="step-nav">' +
      '<button type="submit" class="btn btn-primary btn-lg btn-block" data-submit>' + (nextLabel || '다음') + '</button>' +
      (noBack ? '' : '<button type="button" class="btn-text" data-back>이전으로</button>') + '</div>';
  }

  function err(id) { return '<p class="field-error" id="' + id + '" role="alert" hidden></p>'; }
  function showErr(id, msg, input) {
    var el = document.getElementById(id);
    el.textContent = msg; el.hidden = false;
    if (input) { input.setAttribute('aria-invalid', 'true'); input.focus(); }
    return false;
  }

  /* ---------- 화면들 ---------- */
  var VIEWS = {
    method: function () {
      var kakao = cfg.kakao
        ? '<a class="btn btn-kakao" href="' + G.kakaoUrl(nextPage) + '">' + KAKAO + '카카오로 시작하기</a><div class="divider-text">또는</div>'
        : '';
      return (notice ? '<p class="alert" role="alert">' + G.esc(notice) + '</p>' : '') +
        '<h1 class="page-title" tabindex="-1" data-focus>건강한통 시작하기</h1>' +
        '<p class="page-sub">처음이시면 가입이, 이미 가입하셨으면 로그인이 돼요. 처음 가입하신 방법으로 눌러 주세요.</p>' +
        '<div class="method-buttons">' + kakao +
        '<button type="button" class="btn btn-ghost" data-method="phone">' + PHONE + '휴대폰 번호로 시작하기</button>' +
        '</div>' +
        '<div class="reassure">' +
        '<span>' + CHECK + '비밀번호를 만들 필요가 없어요.</span>' +
        '<span>' + CHECK + '가입비는 없고, 매일 오는 건강 정보는 무료예요.</span>' +
        '<span>' + CHECK + '카카오톡을 안 쓰시면 휴대폰 번호로 가입하고 문자로 받으실 수 있어요.</span>' +
        '</div>';
    },

    phone: function () {
      return progress() +
        '<form data-step="phone" novalidate>' +
        '<h1 class="question" tabindex="-1" data-focus>휴대폰 번호를 알려 주세요</h1>' +
        '<p class="question-help">이 번호로 인증번호를 보내 드려요. 이미 가입하셨다면 같은 번호를 넣으시면 로그인돼요.</p>' +
        '<div class="step-body"><div class="field"><label for="f-phone">휴대폰 번호</label>' +
        '<input id="f-phone" type="tel" inputmode="numeric" autocomplete="tel" placeholder="010-0000-0000" value="' + G.esc(state.phone) + '" aria-describedby="e-phone">' + err('e-phone') + '</div></div>' +
        nav('인증번호 받기') + '</form>';
    },

    code: function () {
      var dev = cfg.sms_console
        ? '<p class="alert alert-dev">개발용 서버라 문자는 실제로 보내지 않아요. 서버를 켠 창에 찍힌 숫자 6자리를 넣어 주세요.</p>'
        : '';
      return progress() +
        '<form data-step="code" novalidate>' +
        '<h1 class="question" tabindex="-1" data-focus>문자로 받은 숫자 6자리를 넣어 주세요</h1>' +
        '<p class="question-help">' + G.esc(state.phone) + '(으)로 보냈어요. 5분 안에 넣어 주세요.</p>' + dev +
        '<div class="step-body"><div class="field"><label for="f-code">인증번호</label>' +
        '<input id="f-code" class="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" aria-describedby="e-code">' + err('e-code') +
        '<p class="field-help">문자가 안 오면 <button type="button" class="btn-text" data-resend>다시 보내기</button></p></div></div>' +
        nav('확인') + '</form>';
    },

    name: function () {
      var help = state.method === 'kakao' && state.name
        ? '카카오에 등록된 이름을 불러왔어요. 다른 이름으로 불러 드리길 원하시면 고쳐 주세요.'
        : '매일 아침 인사에 이 이름을 써요.';
      return progress() +
        '<form data-step="name" novalidate>' +
        '<h1 class="question" tabindex="-1" data-focus>' + (state.method === 'kakao' ? '처음 오셨네요. 어떻게 불러 드릴까요?' : '어떻게 불러 드릴까요?') + '</h1>' +
        '<p class="question-help">' + help + '</p>' +
        '<div class="step-body"><div class="field"><label for="f-name">이름</label>' +
        '<input id="f-name" type="text" autocomplete="name" maxlength="20" placeholder="예: 김순자" value="' + G.esc(state.name) + '" aria-describedby="e-name">' + err('e-name') + '</div></div>' +
        nav('다음', true) + '</form>';
    },

    interests: function () {
      var chips = INTERESTS.map(function (t) {
        var on = state.interests.indexOf(t) >= 0;
        return '<label class="choice"><input type="checkbox" name="interest" value="' + t + '"' + (on ? ' checked' : '') + '><span>' + t + '</span></label>';
      }).join('');
      var none = state.interests.length === 1 && state.interests[0] === '특별히 없어요';
      return progress() +
        '<form data-step="interests" novalidate>' +
        '<h1 class="question" tabindex="-1" data-focus>요즘 신경 쓰이는 건강을 골라 주세요</h1>' +
        '<p class="question-help">여러 개 고르셔도 돼요. 고르신 것과 관련된 정보를 더 자주 보내 드려요.</p>' +
        '<div class="step-body"><fieldset style="border:0;padding:0;margin:0"><legend class="sr-only">관심 건강</legend>' +
        '<div class="choice-grid cols-3">' + chips + '</div>' +
        '<label class="choice" style="margin-top:.65rem"><input type="checkbox" name="interest-none" value="특별히 없어요"' + (none ? ' checked' : '') + '><span>특별히 없어요</span></label>' +
        '</fieldset>' + err('e-int') + '</div>' +
        nav() + '</form>';
    },

    delivery: function () {
      function radio(name, value, label, sub, checked) {
        return '<label class="choice"><input type="radio" name="' + name + '" value="' + value + '"' + (checked ? ' checked' : '') + '><span>' + label + (sub ? '<small>' + sub + '</small>' : '') + '</span></label>';
      }
      var channel = state.method === 'kakao'
        ? '<p class="question-help" style="margin:0 0 .4rem">카카오톡으로 보내 드려요. 문자로 받고 싶으시면 휴대폰 번호로 가입해 주세요.</p>'
        : '<fieldset style="border:0;padding:0;margin:0"><legend class="field" style="font-weight:700;margin-bottom:.6rem">받는 방법</legend><div class="choice-grid">' +
          radio('channel', 'kakao', '카카오톡으로 받기', '사진과 버튼이 함께 와요', state.channel === 'kakao') +
          radio('channel', 'sms', '문자로 받기', '카카오톡을 안 쓰셔도 돼요', state.channel === 'sms') +
          '</div></fieldset>';
      return progress() +
        '<form data-step="delivery" novalidate>' +
        '<h1 class="question" tabindex="-1" data-focus>' + (state.method === 'kakao' ? '몇 시에 받으실래요?' : '어떻게, 몇 시에 받으실래요?') + '</h1>' +
        '<p class="question-help">나중에 내 설정에서 언제든 바꿀 수 있어요.</p>' +
        '<div class="step-body">' + channel +
        '<fieldset style="border:0;padding:0;margin:1rem 0 0"><legend class="field" style="font-weight:700;margin-bottom:.6rem">받는 시간</legend><div class="choice-grid cols-3">' +
        radio('time', '7', '아침 7시', '', state.time === '7') +
        radio('time', '8', '아침 8시', '가장 많이 골라요', state.time === '8') +
        radio('time', '9', '아침 9시', '', state.time === '9') +
        '</div></fieldset></div>' + nav() + '</form>';
    },

    agree: function () {
      var items = [
        ['a-terms', true, '이용약관에 동의해요.'],
        ['a-privacy', true, '개인정보 수집·이용에 동의해요. (이름, 연락처)'],
        ['a-health', true, '고르신 관심 건강을 맞춤 정보에 쓰는 데 동의해요.'],
        ['a-news', false, '새 소식과 혜택 안내를 받을게요.']
      ];
      return progress() +
        '<form data-step="agree" novalidate>' +
        '<h1 class="question" tabindex="-1" data-focus>마지막으로 동의해 주세요</h1>' +
        '<p class="question-help">‘모두 동의’ 한 번이면 돼요.</p>' +
        '<div class="step-body">' +
        '<label class="check check-all"><input type="checkbox" id="a-all"><span>아래 내용에 모두 동의해요</span></label>' +
        '<div class="check-list">' + items.map(function (it) {
          return '<label class="check"><input type="checkbox" class="agree" id="' + it[0] + '" data-required="' + it[1] + '"><span><span class="' + (it[1] ? 'req' : 'opt') + '">' + (it[1] ? '[필수]' : '[선택]') + '</span>' + it[2] + '</span></label>';
        }).join('') + '</div>' + err('e-agree') + '</div>' +
        nav('가입 마치기') + '</form>';
    },

    done: function () {
      var u = state.user;
      var channel = u.channel === 'sms' ? '문자' : '카카오톡';
      var channelBy = u.channel === 'sms' ? '문자로' : '카카오톡으로';
      return '<div class="done">' + DONE +
        '<h1 class="page-title" tabindex="-1" data-focus>' + G.esc(u.name) + '님, 반가워요</h1>' +
        '<p>내일 아침 ' + u.time + '시에 첫 번째 건강 한 통을 ' + channelBy + ' 보내 드릴게요.</p>' +
        '<dl class="summary-list">' +
        '<div><dt>받는 방법</dt><dd>' + channel + '</dd></div>' +
        '<div><dt>받는 시간</dt><dd>매일 아침 ' + u.time + '시</dd></div>' +
        '<div><dt>관심 건강</dt><dd>' + G.esc(u.interests.join(', ')) + '</dd></div>' +
        '</dl>' +
        '<a class="btn btn-primary btn-lg" href="' + nextPage + '">' + goLabel + '</a>' +
        '<a class="btn-text" href="index.html">처음 화면으로</a></div>';
    },

    welcomeBack: function () {
      return '<div class="done">' + DONE +
        '<h1 class="page-title" tabindex="-1" data-focus>' + G.esc(state.user.name) + '님, 다시 오셨네요</h1>' +
        '<p>로그인됐어요. 잠시 뒤 ' + (nextPage.indexOf('membership') === 0 ? '멤버십 신청' : '내 건강정보함') + '으로 이동해요.</p>' +
        '<a class="btn btn-primary btn-lg" href="' + nextPage + '">바로 가기</a></div>';
    },

    loggedIn: function () {
      return '<div class="done"><h1 class="page-title" tabindex="-1" data-focus>' + G.esc(state.user.name) + '님, 이미 로그인되어 있어요</h1>' +
        '<a class="btn btn-primary btn-lg" href="' + nextPage + '">' + (nextPage.indexOf('membership') === 0 ? '멤버십 신청으로' : '내 건강정보함 보기') + '</a>' +
        '<button type="button" class="btn-text" data-logout>다른 계정으로 시작하기 (로그아웃)</button></div>';
    },

    loading: function () {
      return '<p class="muted" style="text-align:center;padding:2rem 0">잠시만 기다려 주세요…</p>';
    }
  };

  /* ---------- 다음으로 넘어가기 ----------
     각 단계는 true(다음 단계로), false(그대로), 또는 Promise 를 돌려준다. */
  var SUBMIT = {
    phone: function (f) {
      var input = f.querySelector('#f-phone');
      if (!G.validPhone(input.value)) return showErr('e-phone', '번호를 다시 확인해 주세요. 예: 010-1234-5678', input);
      var phone = G.fmtPhone(input.value);
      return G.api('POST', 'auth/phone/start', { phone: phone }).then(function (res) {
        state.phone = res.phone;
        G.toast('인증번호를 보냈어요.');
        return true;
      }, function (e) {
        if (e.code === 'cooldown') { state.phone = phone; G.toast(e.message); return true; }   // 방금 보낸 번호가 아직 쓸 수 있다
        return showErr('e-phone', e.message, input);
      });
    },
    code: function (f) {
      var input = f.querySelector('#f-code');
      var code = input.value.trim();
      if (!/^\d{6}$/.test(code)) return showErr('e-code', '숫자 6자리를 넣어 주세요.', input);
      return G.api('POST', 'auth/phone/verify', { phone: state.phone, code: code }).then(function (res) {
        if (res.status === 'logged_in') {
          state.user = res.user;
          G.setUser(res.user);
          return 'welcomeBack';
        }
        state.verified = true;
        return true;
      }, function (e) {
        input.value = '';
        return showErr('e-code', e.message, input);
      });
    },
    name: function (f) {
      var input = f.querySelector('#f-name');
      var v = input.value.trim();
      if (!v) return showErr('e-name', '이름을 적어 주세요.', input);
      state.name = v.slice(0, 20);
      return true;
    },
    interests: function (f) {
      var picked = Array.prototype.map.call(f.querySelectorAll('input[name="interest"]:checked'), function (i) { return i.value; });
      var none = f.querySelector('input[name="interest-none"]').checked;
      if (!picked.length && !none) return showErr('e-int', '하나 이상 골라 주세요. 없으시면 ‘특별히 없어요’를 눌러 주세요.');
      state.interests = picked.length ? picked : ['특별히 없어요'];
      return true;
    },
    delivery: function (f) {
      var ch = f.querySelector('input[name="channel"]:checked');
      state.channel = state.method === 'kakao' ? 'kakao' : (ch ? ch.value : 'sms');
      state.time = f.querySelector('input[name="time"]:checked').value;
      return true;
    },
    agree: function (f) {
      var required = f.querySelectorAll('.agree[data-required="true"]');
      for (var i = 0; i < required.length; i++) {
        if (!required[i].checked) return showErr('e-agree', '[필수] 항목에 모두 동의해 주셔야 가입할 수 있어요.');
      }
      return G.api('POST', 'auth/signup', {
        name: state.name, interests: state.interests, channel: state.channel, time: state.time,
        agree_terms: true, agree_privacy: true, agree_health: true,
        marketing: f.querySelector('#a-news').checked
      }).then(function (res) {
        state.user = res.user;
        G.setUser(res.user);
        return true;
      }, function (e) {
        if (e.code === 'no_pending') { restart(e.message); return false; }
        return showErr('e-agree', e.message);
      });
    }
  };

  /* ---------- 그리기 ---------- */
  function render(view) {
    var name = view || (state.method ? steps[idx] : 'method');
    flow.innerHTML = VIEWS[name]();
    var focus = flow.querySelector('[data-focus]');
    if (focus) focus.focus({ preventScroll: false });
    window.scrollTo(0, 0);
    wire(name);
    if (name === 'welcomeBack') setTimeout(function () { location.href = nextPage; }, 1800);
  }

  function busy(form, on) {
    var btn = form.querySelector('[data-submit]');
    if (!btn) return;
    if (on) { btn.setAttribute('data-label', btn.textContent); btn.textContent = '잠시만요…'; btn.disabled = true; }
    else { btn.textContent = btn.getAttribute('data-label') || btn.textContent; btn.disabled = false; }
  }

  function wire(name) {
    Array.prototype.forEach.call(flow.querySelectorAll('[data-method]'), function (b) {
      b.addEventListener('click', function () { notice = ''; begin(b.getAttribute('data-method')); });
    });
    var back = flow.querySelector('[data-back]');
    if (back) back.addEventListener('click', function () {
      if (idx === 0) restart(); else { idx -= 1; render(); }
    });
    var resend = flow.querySelector('[data-resend]');
    if (resend) resend.addEventListener('click', function () {
      resend.disabled = true;
      G.api('POST', 'auth/phone/start', { phone: state.phone }).then(function () {
        G.toast('인증번호를 다시 보냈어요.');
      }, function (e) { G.toast(e.message); }).then(function () { resend.disabled = false; });
    });

    var phone = flow.querySelector('#f-phone');
    if (phone) phone.addEventListener('input', function () { phone.value = G.fmtPhone(phone.value); });
    var code = flow.querySelector('#f-code');
    if (code) code.addEventListener('input', function () { code.value = code.value.replace(/\D/g, '').slice(0, 6); });

    if (name === 'interests') {
      var none = flow.querySelector('input[name="interest-none"]');
      var boxes = flow.querySelectorAll('input[name="interest"]');
      none.addEventListener('change', function () { if (none.checked) Array.prototype.forEach.call(boxes, function (b) { b.checked = false; }); });
      Array.prototype.forEach.call(boxes, function (b) { b.addEventListener('change', function () { if (b.checked) none.checked = false; }); });
    }
    if (name === 'agree') {
      var all = flow.querySelector('#a-all');
      var agrees = Array.prototype.slice.call(flow.querySelectorAll('.agree'));
      all.addEventListener('change', function () { agrees.forEach(function (a) { a.checked = all.checked; }); });
      agrees.forEach(function (a) { a.addEventListener('change', function () { all.checked = agrees.every(function (x) { return x.checked; }); }); });
    }

    var form = flow.querySelector('form');
    if (form) form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('[data-submit]');
      if (btn && btn.disabled) return;
      var errs = form.querySelectorAll('.field-error');
      Array.prototype.forEach.call(errs, function (el) { el.hidden = true; });
      Array.prototype.forEach.call(form.querySelectorAll('[aria-invalid]'), function (el) { el.removeAttribute('aria-invalid'); });
      busy(form, true);
      Promise.resolve(SUBMIT[name](form)).then(function (result) {
        if (!form.isConnected) return;   // 처음 화면으로 돌아간 경우
        busy(form, false);
        if (result === 'welcomeBack') { render('welcomeBack'); return; }
        if (result !== true) return;
        idx += 1;
        render();
      });
    });
  }

  /* ---------- 시작 ---------- */
  flow.innerHTML = VIEWS.loading();
  Promise.all([G.me(), G.config()]).then(function (r) {
    var user = r[0];
    cfg = r[1];
    if (devNote && (cfg.sms_console || cfg.kakao_practice)) {
      devNote.innerHTML = '<b>개발용 서버예요.</b> ' +
        (cfg.sms_console ? '인증 문자는 실제로 보내지 않고 서버 창에 찍혀요. ' : '') +
        (cfg.kakao_practice ? '카카오 로그인은 연습 화면으로 열려요.' : '');
      devNote.hidden = false;
    }
    if (user) { state.user = user; render('loggedIn'); return; }

    var error = G.param('error');
    if (error) notice = ERRORS[error] || '로그인하지 못했어요. 다시 해 주세요.';
    if (G.param('step') === 'profile') {
      G.api('GET', 'auth/pending').then(beginProfile, function (e) { restart(e.message); });
      return;
    }
    var m = G.param('method');
    if (m === 'kakao' && cfg.kakao && !error) { location.replace(G.kakaoUrl(nextPage)); return; }
    if (m === 'phone') begin('phone'); else render('method');
  }, function (e) {
    flow.outerHTML = G.problemPanel(e);
  });
})();
