/* 멤버십 신청: 로그인한 회원 본인 계정으로 신청.
   결제(PG) 연결은 다음 단계라, 지금은 신청 화면만 보여 주고 결제 버튼을 누르면 '준비 중'이라고 알린다. */
(function () {
  'use strict';
  var G = window.GHT;
  var app = document.getElementById('app');
  var KAKAO = '<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4C7 4 3 7.2 3 11.1c0 2.5 1.6 4.6 4.1 5.9L6.3 20.5l4-2.6c.6.1 1.1.1 1.7.1 5 0 9-3.2 9-7S17 4 12 4z" fill="currentColor"/></svg>';
  var CHECK = '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

  function gate() {
    app.innerHTML = '<section class="panel" style="text-align:center">' +
      '<h1 class="page-title">멤버십은 가입 후에 신청할 수 있어요</h1>' +
      '<p class="page-sub">1분이면 끝나요. 비밀번호는 필요 없어요.</p>' +
      '<div class="method-buttons" style="max-width:26rem;margin-inline:auto">' +
      '<a class="btn btn-kakao" href="' + G.kakaoUrl('membership.html') + '">' + KAKAO + '카카오로 시작하기</a>' +
      '<a class="btn btn-ghost" href="' + G.phoneUrl('membership.html') + '">휴대폰 번호로 시작하기</a></div>' +
      '<p class="muted small" style="margin-top:1.4rem">이미 가입하셨으면 같은 버튼으로 로그인돼요.</p></section>';
  }

  function member(user) {
    app.innerHTML = '<section class="panel"><div class="done">' +
      '<div class="done-icon">' + CHECK + '</div>' +
      '<h1 class="page-title">' + G.esc(user.name) + '님은 이미 멤버십 회원이에요</h1>' +
      '<a class="btn btn-primary btn-lg" href="my.html">내 건강정보함으로</a>' +
      '<a class="btn-text" href="my.html#settings">내 설정 열기</a></div></section>';
  }

  function form(user) {
    var METHODS = ['카카오페이', '네이버페이', '신용·체크카드', '휴대폰 결제'];
    var AGREES = [
      ['m-billing', '매월 3,900원이 자동으로 결제되는 데 동의해요. 결제 3일 전에 미리 알려 드리고, 언제든 해지할 수 있어요.'],
      ['m-terms', '멤버십 이용약관에 동의해요.'],
      ['m-health', '상담을 위해 말씀하신 건강 상태를 처리하는 데 동의해요.'],
      ['m-abroad', '상담 제공을 위한 개인정보 국외 이전에 동의해요.']
    ];

    app.innerHTML =
      '<h1 class="page-title">멤버십 신청</h1>' +
      '<p class="page-sub">' + G.esc(user.name) + '님 계정으로 신청해요.</p>' +
      '<form class="panel" style="margin-top:1.8rem" novalidate id="pay">' +
      '<div class="member-summary"><div><div class="ms-name">건강한통 멤버십</div><ul>' +
      '<li>건강 맞춤 상담, 하루 3번</li><li>내 몸에 맞춘 정보, 일주일에 2~3번 더</li><li>주간 건강 특집과 나라 혜택 알림</li><li>약과 영양제, 같이 먹어도 되는지 확인</li></ul></div>' +
      '<div class="ms-price"><span>3,900</span>원 / 월</div></div>' +

      '<div class="form-section" style="margin-top:2rem"><h2>결제 방법</h2><fieldset style="border:0;padding:0;margin:0"><legend class="sr-only">결제 방법</legend><div class="choice-grid">' +
      METHODS.map(function (m, i) {
        return '<label class="choice"><input type="radio" name="method" value="' + m + '"' + (i === 0 ? ' checked' : '') + '><span>' + m + '</span></label>';
      }).join('') +
      '</div></fieldset></div>' +

      '<div class="form-section"><h2>동의</h2>' +
      '<label class="check check-all"><input type="checkbox" id="m-all"><span>아래 내용에 모두 동의해요</span></label>' +
      '<div class="check-list">' + AGREES.map(function (a) {
        return '<label class="check"><input type="checkbox" class="agree" id="' + a[0] + '"><span><span class="req">[필수]</span>' + a[1] + '</span></label>';
      }).join('') + '</div>' +
      '<p class="field-error" id="e-agree" role="alert" hidden></p></div>' +

      '<div class="form-section"><div class="total"><div><div class="total-label">매월 결제 금액</div>' +
      '<div class="total-next">결제 3일 전에 미리 알려 드려요</div></div>' +
      '<div class="total-num">3,900원</div></div>' +
      '<button type="submit" class="btn btn-primary btn-lg btn-block" style="margin-top:1.6rem">3,900원 결제하기</button>' +
      '<div id="pay-result" role="status"></div>' +
      '<p class="muted small" style="margin-top:.9rem;text-align:center">언제든 내 설정에서 해지할 수 있어요.</p></div>' +
      '</form>';

    var f = document.getElementById('pay');
    var all = document.getElementById('m-all');
    var agrees = Array.prototype.slice.call(f.querySelectorAll('.agree'));
    var errEl = document.getElementById('e-agree');
    all.addEventListener('change', function () { agrees.forEach(function (a) { a.checked = all.checked; }); if (all.checked) errEl.hidden = true; });
    agrees.forEach(function (a) { a.addEventListener('change', function () { all.checked = agrees.every(function (x) { return x.checked; }); if (all.checked) errEl.hidden = true; }); });

    f.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!agrees.every(function (a) { return a.checked; })) {
        errEl.textContent = '[필수] 항목에 모두 동의해 주셔야 신청할 수 있어요.';
        errEl.hidden = false;
        all.focus();
        return;
      }
      document.getElementById('pay-result').innerHTML =
        '<p class="alert" style="margin-top:1rem">결제는 아직 열리지 않았어요. 결제가 열리면 바로 신청하실 수 있어요. 그동안 매일 아침 건강 정보는 무료로 받아 보세요.</p>';
    });
  }

  app.innerHTML = '<p class="muted" style="text-align:center;padding:3rem 0">잠시만 기다려 주세요…</p>';
  G.me().then(function (user) {
    if (!user) gate();
    else if (user.plan === 'member') member(user);
    else form(user);
  }, function (e) {
    app.innerHTML = G.problemPanel(e);
  });
})();
