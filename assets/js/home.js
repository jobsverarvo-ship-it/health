/* 첫 화면: 나타나는 효과, 휴대폰 아래쪽 시작 버튼, 이번 주 미리 보기 */
(function () {
  'use strict';
  var G = window.GHT;

  /* ---- 화면에 들어올 때 차례로 나타나기 ---- */
  G.reveal([
    '.facts li', '.section-head', '.how figure', '.sms-note', '.diff-row', '.info-top .not-sent', '.cat',
    '.week', '.feature-list li', '.box-intro .btn', '.box-stack > *', '.step', '.center-cta', '.plan',
    '.consult .eyebrow', '#consult-title', '.rules li', '.emergency', '.chat-window', '.process li', '.pledges',
    '#faq-title', '.contact', '.faq-list details', '.final-inner > *'
  ].join(', '));
  G.watch('.process');

  /* ---- 메뉴: 지금 보고 있는 부분을 표시 ---- */
  var nav = document.querySelector('.nav');
  var links = nav ? Array.prototype.slice.call(nav.querySelectorAll('a[href^="#"]')) : [];
  var targets = links.map(function (a) { return document.querySelector(a.getAttribute('href')); });
  var activeLink = null;
  function spy() {

    var line = window.innerHeight * 0.35, found = null;
    targets.forEach(function (sec, i) { if (sec && sec.getBoundingClientRect().top <= line) found = links[i]; });
    if (found === activeLink) return;
    if (activeLink) activeLink.removeAttribute('aria-current');
    activeLink = found;
    if (found) {
      found.setAttribute('aria-current', 'true');
      // 좁은 화면에서 옆으로 넘기는 메뉴라면 표시된 버튼이 보이게 옮긴다
      if (nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: Math.max(0, found.offsetLeft - 16), behavior: 'smooth' });
    }
  }
  if (links.length) {
    window.addEventListener('scroll', spy, { passive: true });
    window.addEventListener('resize', spy);
    spy();
  }

  /* ---- 휴대폰: 첫 화면을 지나면 아래쪽에 '무료로 시작하기'를 띄운다 ---- */
  var sticky = document.getElementById('sticky-cta');
  var hero = document.querySelector('.hero'), fin = document.querySelector('.final');
  if (sticky && hero && fin && 'IntersectionObserver' in window) {
    var heroSeen = true, finSeen = false;
    var update = function () {
      var hint = document.getElementById('size-hint');
      var show = !heroSeen && !finSeen && (!hint || hint.hidden);
      sticky.classList.toggle('show', show);
      sticky.inert = !show;
    };
    new IntersectionObserver(function (es) { heroSeen = es[es.length - 1].isIntersecting; update(); }).observe(hero);
    new IntersectionObserver(function (es) { finSeen = es[es.length - 1].isIntersecting; update(); }).observe(fin);
    var hintClose = document.getElementById('size-hint-close');
    if (hintClose) hintClose.addEventListener('click', function () { setTimeout(update, 0); });
    update();
  }

  /* ---- 이번 주 미리 보기 ---- */
  var TIPS = window.GHT_TIPS || [];
  var byId = {};
  TIPS.forEach(function (t) { byId[t.id] = t; });
  // 월요일부터 일요일까지 요일별 주제에 맞춘 정보
  var WEEK = ['t02', 't03', 't04', 't01', 't05', 't06', 't07'].map(function (id) { return byId[id]; });
  var NAMES = ['월', '화', '수', '목', '금', '토', '일'];
  var daysEl = document.getElementById('days');
  if (!daysEl || WEEK.some(function (t) { return !t; })) return;

  var todayIdx = (new Date().getDay() + 6) % 7;
  var current = todayIdx;

  var btns = WEEK.map(function (t, i) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'day';
    b.id = 'day-' + i;
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-controls', 'tip-panel');
    b.innerHTML = '<span class="day-name"><span class="long">' + NAMES[i] + '요일</span><span class="short">' + NAMES[i] + '</span>' +
      (i === todayIdx ? '<span class="today-dot">오늘</span>' : '') + '</span><span class="day-cat">' + G.esc(G.CATS[t.cat]) + '</span>';
    b.addEventListener('click', function () { select(i); });
    b.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); select((i + 1) % 7, true); }
      if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); select((i + 6) % 7, true); }
    });
    daysEl.appendChild(b);
    return b;
  });

  var panel = document.getElementById('tip-panel');
  function select(i, focus) {
    var changed = current !== i;
    current = i;
    var t = WEEK[i];
    if (changed) { panel.classList.remove('swap'); void panel.offsetWidth; panel.classList.add('swap'); }
    btns.forEach(function (b, j) { b.setAttribute('aria-selected', String(i === j)); b.tabIndex = i === j ? 0 : -1; });
    document.getElementById('tip-panel').setAttribute('aria-labelledby', 'day-' + i);
    document.getElementById('tip-cat').textContent = G.CATS[t.cat];
    document.getElementById('tip-day').textContent = NAMES[i] + '요일 아침' + (i === todayIdx ? ' · 오늘' : '');
    document.getElementById('tip-title').textContent = t.title;
    document.getElementById('tip-body').textContent = t.body;
    document.getElementById('tip-action').textContent = t.action;
    if (focus) btns[i].focus();
  }
  select(todayIdx);

  var listen = document.getElementById('tip-listen');
  if (listen) listen.addEventListener('click', function () {
    var t = WEEK[current];
    G.speak(t.title + '. ' + t.body + ' 오늘 이렇게 해 보세요. ' + t.action, listen);
  });
})();
