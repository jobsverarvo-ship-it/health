/* 내 건강정보함: 오늘 · 지난 정보 · 저장한 정보 · 내 설정
   로그인한 회원만 볼 수 있고, 정보와 설정은 모두 서버에서 받아 온다. */
(function () {
  'use strict';
  var G = window.GHT;
  var app = document.getElementById('app');
  var INTERESTS = ['혈압', '당뇨', '관절·뼈', '심장', '눈', '귀', '기억력', '수면', '소화'];

  var ICON = {
    speak: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    star: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.8l2.5 5.1 5.6.8-4 3.9.9 5.6-5-2.6-5 2.6.9-5.6-4-3.9 5.6-.8z"/></svg>',
    starOn: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.8l2.5 5.1 5.6.8-4 3.9.9 5.6-5-2.6-5 2.6.9-5.6-4-3.9 5.6-.8z"/></svg>',
    send: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12l16-8-6 16-2.5-6.5z"/><path d="M11.5 13.5 20 4"/></svg>',
    check: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chevron: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
    kakao: '<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4C7 4 3 7.2 3 11.1c0 2.5 1.6 4.6 4.1 5.9L6.3 20.5l4-2.6c.6.1 1.1.1 1.7.1 5 0 9-3.2 9-7S17 4 12 4z" fill="currentColor"/></svg>'
  };

  var user = null;
  var TIPS = [];
  var savedIds = [];

  /* ---------- 로그인 안 했을 때 ---------- */
  function gate() {
    app.innerHTML = '<section class="panel" style="text-align:center">' +
      '<h1 class="page-title">로그인하시면<br>받은 건강 정보를 모두 볼 수 있어요</h1>' +
      '<p class="page-sub">처음 가입하신 방법으로 눌러 주세요. 비밀번호는 필요 없어요.</p>' +
      '<div class="method-buttons" style="max-width:26rem;margin-inline:auto">' +
      '<a class="btn btn-kakao" href="' + G.kakaoUrl('my.html') + '">' + ICON.kakao + '카카오로 로그인</a>' +
      '<a class="btn btn-ghost" href="' + G.phoneUrl('my.html') + '">휴대폰 번호로 로그인</a></div>' +
      '<p class="muted small" style="margin-top:1.4rem">아직 회원이 아니시면 같은 버튼으로 바로 가입돼요.</p></section>';
  }

  /* ---------- 공통 ---------- */
  function isSaved(id) { return savedIds.indexOf(id) >= 0; }
  function dayLabel(t) {
    if (t.daysAgo === 0) return '오늘 · ' + G.fmtDate(t.dateObj);
    if (t.daysAgo === 1) return '어제 · ' + G.fmtDate(t.dateObj);
    return G.fmtDate(t.dateObj);
  }
  function speakText(t) {
    return t.title + '. ' + t.body + ' 오늘 이렇게 해 보세요. ' + t.action + (t.caution ? '. ' + t.caution : '');
  }
  function shareText(t) { return t.body + '\n오늘 이렇게 해 보세요: ' + t.action; }
  function saveBtn(t) {
    var on = isSaved(t.id);
    return '<button type="button" class="tool" data-act="save" data-id="' + t.id + '" aria-pressed="' + on + '">' + (on ? ICON.starOn : ICON.star) + '<span>' + (on ? '저장했어요' : '저장') + '</span></button>';
  }
  function tools(t) {
    return '<div class="tools">' +
      '<button type="button" class="tool" data-act="speak" data-id="' + t.id + '">' + ICON.speak + '<span data-label>소리로 듣기</span></button>' +
      saveBtn(t) +
      '<button type="button" class="tool" data-act="share" data-id="' + t.id + '">' + ICON.send + '<span>가족에게 보내기</span></button>' +
      '</div>';
  }
  function detail(t) {
    return '<p>' + G.esc(t.body) + '</p>' +
      '<div class="tip-action">' + ICON.check + '<div><div class="tip-action-label">오늘 이렇게 해 보세요</div><p>' + G.esc(t.action) + '</p></div></div>' +
      (t.caution ? '<p class="tip-caution">' + G.esc(t.caution) + '</p>' : '') +
      (t.source ? '<p class="tip-source">출처: ' + G.esc(t.source) + '</p>' : '') + tools(t);
  }
  function item(t) {
    return '<details class="item" data-id="' + t.id + '"><summary>' +
      '<span><span class="item-cat">' + G.esc(G.CATS[t.cat]) + '</span><span class="item-title">' + G.esc(t.title) +
      (isSaved(t.id) ? ' <span class="item-star" aria-label="저장함">★</span>' : '') + '</span></span>' +
      '<span class="item-open" aria-hidden="true">' + ICON.chevron + '</span></summary>' +
      '<div class="item-body">' + detail(t) + '</div></details>';
  }
  function listByDay(list, emptyMsg) {
    if (!list.length) return '<div class="empty">' + emptyMsg + '</div>';
    var html = '', last = null;
    list.forEach(function (t) {
      if (t.daysAgo !== last) {
        if (last !== null) html += '</div>';
        html += '<div class="day-group"><p class="day-label">' + dayLabel(t) + '</p>';
        last = t.daysAgo;
      }
      html += item(t);
    });
    return html + '</div>';
  }
  function greeting() {
    var h = new Date().getHours();
    return h < 11 ? '좋은 아침이에요' : h < 18 ? '좋은 오후예요' : '편안한 저녁 되세요';
  }

  /* ---------- 탭 화면 ---------- */
  var filter = { q: '', cat: 'all' };

  var TABS = {
    today: function () {
      var t = TIPS[0];
      if (!t) return '<div class="empty">아직 받은 정보가 없어요. 내일 아침에 첫 정보를 보내 드릴게요.</div>';
      var html = '<article class="tip-card" style="background:#fff">' +
        '<div class="tip-meta"><span class="chip">' + G.esc(G.CATS[t.cat]) + '</span><span class="tip-day">오늘 아침 ' + user.time + '시에 보내 드린 정보</span></div>' +
        '<h2 class="tip-title">' + G.esc(t.title) + '</h2>' +
        '<div class="tip-body">' + detail(t) + '</div></article>';
      if (user.paused) html = '<div class="empty" style="margin-bottom:1rem">지금은 건강 정보를 잠시 멈춰 두셨어요. 내 설정에서 다시 받기를 켜실 수 있어요.</div>' + html;
      if (user.plan !== 'member') {
        html += '<div class="upsell"><div><strong>궁금한 게 생기면 물어보세요</strong><p>멤버십이면 건강 상담을 하루 3번까지 받을 수 있어요. 월 3,900원.</p></div>' +
          '<a class="btn btn-light btn-sm" href="membership.html">멤버십 알아보기</a></div>';
      }
      html += '<p class="muted small" style="margin-top:1.6rem">지난 정보는 위쪽 ‘지난 정보’에서 날짜별로 보실 수 있어요.</p>';
      return html;
    },

    archive: function () {
      var chips = '<button type="button" class="fchip" data-cat="all" aria-pressed="' + (filter.cat === 'all') + '">전체</button>' +
        Object.keys(G.CATS).map(function (k) {
          return '<button type="button" class="fchip" data-cat="' + k + '" aria-pressed="' + (filter.cat === k) + '">' + G.esc(G.CATS[k]) + '</button>';
        }).join('');
      return '<form class="search" role="search" data-search><div class="field"><label class="sr-only" for="q">찾고 싶은 말</label>' +
        '<input id="q" type="search" placeholder="찾고 싶은 말 (예: 혈압)" value="' + G.esc(filter.q) + '"></div></form>' +
        '<div class="filter-chips" aria-label="주제로 고르기">' + chips + '</div>' +
        '<div id="results">' + results() + '</div>';
    },

    saved: function () {
      var list = TIPS.filter(function (t) { return isSaved(t.id); });
      return listByDay(list, '아직 저장한 정보가 없어요.<br>마음에 드는 정보에서 ‘저장’을 눌러 보세요.');
    },

    settings: function () {
      function radio(name, value, label, checked) {
        return '<label class="choice"><input type="radio" name="' + name + '" value="' + value + '"' + (checked ? ' checked' : '') + '><span>' + label + '</span></label>';
      }
      var chips = INTERESTS.map(function (t) {
        return '<label class="choice"><input type="checkbox" name="interest" value="' + t + '"' + (user.interests.indexOf(t) >= 0 ? ' checked' : '') + '><span>' + t + '</span></label>';
      }).join('');
      var channel = user.phone
        ? '<p>카카오톡이 불편하시면 문자로 바꾸실 수 있어요.</p><div class="choice-grid">' +
          radio('channel', 'kakao', '카카오톡', user.channel === 'kakao') + radio('channel', 'sms', '문자', user.channel === 'sms') + '</div>'
        : '<p>카카오톡으로 받고 계세요. 문자로 받으시려면 휴대폰 번호로 가입하셔야 해요.</p>';
      return '<form data-settings novalidate>' +
        '<div class="setting"><h3>받는 시간</h3><p>매일 이 시간에 보내 드려요.</p><div class="choice-grid cols-3">' +
        radio('time', '7', '아침 7시', user.time === '7') + radio('time', '8', '아침 8시', user.time === '8') + radio('time', '9', '아침 9시', user.time === '9') + '</div></div>' +
        '<div class="setting"><h3>받는 방법</h3>' + channel + '</div>' +
        '<div class="setting"><h3>관심 건강</h3><p>고르신 것과 관련된 정보를 더 자주 보내 드려요.</p><div class="choice-grid cols-3">' + chips + '</div></div>' +
        '<div class="setting"><div class="switch-row"><div><h3>건강 정보 잠시 멈추기</h3><p style="color:var(--ink-2);font-size:.95rem">여행이나 입원 중에는 잠시 멈춰 두세요. 다시 켜면 다음 날부터 와요.</p></div>' +
        '<label class="switch"><input type="checkbox" name="paused"' + (user.paused ? ' checked' : '') + ' aria-label="건강 정보 잠시 멈추기"><span></span></label></div></div>' +
        '<div class="settings-actions"><button type="submit" class="btn btn-primary" data-submit>바꾼 내용 저장하기</button></div>' +
        '</form>' +
        '<div class="setting" style="margin-top:2rem;border-top:1px solid var(--line);padding-top:2rem"><h3>멤버십</h3>' +
        (user.plan === 'member'
          ? '<p>멤버십 이용 중이에요.</p>'
          : '<p>지금은 무료로 이용 중이에요.</p><a class="btn btn-ghost btn-sm" href="membership.html">멤버십 알아보기</a>') +
        '</div>' +
        '<div class="setting"><h3>계정</h3><p>' + G.esc(user.name) + '님 · ' + (user.method === 'kakao' ? '카카오로 가입' : '휴대폰 번호로 가입 (' + G.esc(user.phone) + ')') + '</p>' +
        '<div class="tools"><button type="button" class="tool" data-logout>로그아웃</button><button type="button" class="tool" data-delete>회원 탈퇴</button></div><div id="delete-box"></div></div>';
    }
  };

  function results() {
    var q = filter.q.trim();
    var list = TIPS.filter(function (t) {
      if (filter.cat !== 'all' && t.cat !== filter.cat) return false;
      if (!q) return true;
      return (t.title + ' ' + t.body + ' ' + t.action).indexOf(q) >= 0;
    });
    var head = '<p class="muted small" style="margin-bottom:1rem">' + (q || filter.cat !== 'all' ? '찾은 정보 ' : '지금까지 받은 정보 ') + list.length + '개</p>';
    return head + listByDay(list, q ? '‘' + G.esc(q) + '’(이)가 들어간 정보가 없어요. 다른 말로 찾아보세요.' : '이 주제로 받은 정보가 아직 없어요.');
  }

  /* ---------- 화면 틀 ---------- */
  function shell() {
    var member = user.plan === 'member';
    app.innerHTML =
      '<div class="greet"><div><p class="greet-date">' + G.fmtDate(new Date()) + '</p>' +
      '<h1 class="page-title">' + G.esc(user.name) + '님, ' + greeting() + '</h1></div>' +
      '<span class="plan-pill' + (member ? ' member' : '') + '">' + (member ? '멤버십 회원' : '무료 회원') + '</span></div>' +
      '<div class="tabs" role="tablist" aria-label="정보함 메뉴">' +
      tab('today', '오늘의 건강 한 통') +
      tab('archive', '지난 정보', TIPS.length) +
      tab('saved', '저장한 정보', savedIds.length) +
      tab('settings', '내 설정') +
      '</div><div id="view" role="tabpanel"></div>';
    Array.prototype.forEach.call(app.querySelectorAll('.tab'), function (b) {
      b.addEventListener('click', function () { location.hash = b.getAttribute('data-tab'); });
    });
  }
  function tab(id, label, count) {
    return '<button type="button" class="tab" role="tab" id="tab-' + id + '" data-tab="' + id + '" aria-selected="false">' + label +
      (count != null ? '<span class="count" data-count="' + id + '">' + count + '</span>' : '') + '</button>';
  }

  function current() {
    var h = (location.hash || '').replace('#', '');
    return TABS[h] ? h : 'today';
  }
  function show() {
    var name = current();
    Array.prototype.forEach.call(app.querySelectorAll('.tab'), function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-tab') === name)); });
    var view = document.getElementById('view');
    view.setAttribute('aria-labelledby', 'tab-' + name);
    view.innerHTML = TABS[name]();
    wire(name);
  }
  function updateCounts() {
    var c = app.querySelector('[data-count="saved"]');
    if (c) c.textContent = savedIds.length;
  }
  function sessionLost(e) {
    if (e && e.status === 401) {
      G.toast('로그인 시간이 지났어요. 다시 로그인해 주세요.');
      G.setUser(null);
      setTimeout(gate, 600);
      return true;
    }
    return false;
  }

  /* ---------- 동작 ---------- */
  function wire(name) {
    var view = document.getElementById('view');
    if (name === 'archive') {
      var input = view.querySelector('#q');
      var form = view.querySelector('[data-search]');
      form.addEventListener('submit', function (e) { e.preventDefault(); });
      input.addEventListener('input', function () { filter.q = input.value; document.getElementById('results').innerHTML = results(); });
      Array.prototype.forEach.call(view.querySelectorAll('.fchip'), function (b) {
        b.addEventListener('click', function () {
          filter.cat = b.getAttribute('data-cat');
          Array.prototype.forEach.call(view.querySelectorAll('.fchip'), function (x) { x.setAttribute('aria-pressed', String(x === b)); });
          document.getElementById('results').innerHTML = results();
        });
      });
    }
    if (name === 'settings') wireSettings(view);
  }

  // 소리로 듣기 · 저장 · 보내기 (모든 탭 공통)
  app.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('[data-act]') : null;
    if (!btn) return;
    var t = TIPS.filter(function (x) { return x.id === btn.getAttribute('data-id'); })[0];
    if (!t) return;
    var act = btn.getAttribute('data-act');
    if (act === 'speak') G.speak(speakText(t), btn);
    if (act === 'share') G.share(t.title, shareText(t));
    if (act === 'save') {
      if (btn.disabled) return;
      var on = !isSaved(t.id);
      btn.disabled = true;
      G.api(on ? 'PUT' : 'DELETE', 'me/saved/' + encodeURIComponent(t.id)).then(function (res) {
        savedIds = res.ids;
        btn.outerHTML = saveBtn(t);
        G.toast(on ? '저장한 정보에 넣었어요.' : '저장한 정보에서 뺐어요.');
        updateCounts();
        if (current() === 'saved' && !on) show();
      }, function (err) {
        btn.disabled = false;
        if (!sessionLost(err)) G.toast(err.message);
      });
    }
  });

  function wireSettings(view) {
    var form = view.querySelector('[data-settings]');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var submit = form.querySelector('[data-submit]');
      if (submit.disabled) return;
      var picked = Array.prototype.map.call(form.querySelectorAll('input[name="interest"]:checked'), function (i) { return i.value; });
      var ch = form.querySelector('input[name="channel"]:checked');
      var body = {
        time: form.querySelector('input[name="time"]:checked').value,
        interests: picked.length ? picked : ['특별히 없어요'],
        paused: form.querySelector('input[name="paused"]').checked
      };
      if (ch) body.channel = ch.value;
      submit.disabled = true;
      submit.textContent = '저장하는 중…';
      G.api('PATCH', 'me', body).then(function (res) {
        user = res.user;
        G.setUser(user);
        G.toast(user.paused ? '저장했어요. 건강 정보를 잠시 멈춰 둘게요.' : '저장했어요. 다음 날 아침부터 바뀐 대로 보내 드려요.');
      }, function (err) {
        if (!sessionLost(err)) G.toast(err.message);
      }).then(function () {
        submit.disabled = false;
        submit.textContent = '바꾼 내용 저장하기';
      });
    });
    var del = view.querySelector('[data-delete]');
    del.addEventListener('click', function () {
      document.getElementById('delete-box').innerHTML = '<div class="confirm-box">탈퇴하면 가입 정보와 저장한 정보가 모두 지워지고 되돌릴 수 없어요. 정말 탈퇴하시겠어요?' +
        '<div class="tools"><button type="button" class="tool" data-confirm-delete>탈퇴할게요</button><button type="button" class="tool" data-keep-account>아니요</button></div></div>';
      var yes = view.querySelector('[data-confirm-delete]');
      yes.addEventListener('click', function () {
        yes.disabled = true;
        G.api('DELETE', 'me').then(function () {
          G.setUser(null);
          G.toast('탈퇴했어요. 그동안 고마웠어요.');
          setTimeout(function () { location.href = 'index.html'; }, 900);
        }, function (err) {
          yes.disabled = false;
          if (!sessionLost(err)) G.toast(err.message);
        });
      });
      view.querySelector('[data-keep-account]').addEventListener('click', function () { document.getElementById('delete-box').innerHTML = ''; });
    });
  }

  /* ---------- 시작 ---------- */
  app.innerHTML = '<p class="muted" style="text-align:center;padding:3rem 0">건강정보함을 여는 중이에요…</p>';
  G.me().then(function (u) {
    if (!u) { gate(); return; }
    user = u;
    return Promise.all([G.api('GET', 'tips'), G.api('GET', 'me/saved')]).then(function (r) {
      var today = new Date(); today.setHours(0, 0, 0, 0);
      TIPS = r[0].tips.map(function (t) {
        var d = G.parseDate(t.date);
        return Object.assign({ dateObj: d, daysAgo: Math.round((today - d) / 86400000) }, t);
      });
      savedIds = r[1].ids;
      shell();
      show();
      window.addEventListener('hashchange', function () { show(); window.scrollTo(0, 0); });
    });
  }).catch(function (e) {
    if (sessionLost(e)) return;
    app.innerHTML = G.problemPanel(e);
  });
})();
