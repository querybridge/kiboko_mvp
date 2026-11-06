/* Kiboko mobile: bottom sheets, tap-to-confirm buttons, toasts, the navigation
   progress bar, the theme toggle and the forecast chart (drawn as SVG at the
   element's real pixel size, so it stays sharp on Retina screens). */
(function () {
  var root = document.documentElement;

  // ---- Theme (shared with the desktop: localStorage 'theme') ----
  var themeColor = document.getElementById('themeColor');
  function paintTheme() {
    var light = root.classList.contains('theme-light');
    if (themeColor) themeColor.content = light ? '#F4F2F8' : '#0E081A';
    var name = document.getElementById('mThemeName');
    if (name) name.textContent = light ? 'Light' : 'Dark';
  }
  paintTheme();
  var toggle = document.getElementById('mThemeToggle');
  if (toggle) toggle.addEventListener('click', function () {
    var light = root.classList.toggle('theme-light');
    try { localStorage.setItem('theme', light ? 'light' : 'dark'); } catch (e) {}
    paintTheme();
    if (window.kbRedrawCharts) window.kbRedrawCharts();
  });

  // ---- Bottom sheets ----
  var scrim = document.getElementById('mScrim'), open = null;
  function closeSheet() {
    if (!open) return;
    var s = open; open = null;
    s.classList.remove('show'); scrim.classList.remove('show');
    setTimeout(function () { s.hidden = true; scrim.hidden = true; }, 280);
  }
  function openSheet(id) {
    var s = document.getElementById(id);
    if (!s) return;
    closeSheet();
    s.hidden = false; scrim.hidden = false;
    requestAnimationFrame(function () { s.classList.add('show'); scrim.classList.add('show'); });
    open = s;
  }
  document.querySelectorAll('[data-sheet]').forEach(function (b) {
    b.addEventListener('click', function () { openSheet(b.dataset.sheet); });
  });
  if (scrim) scrim.addEventListener('click', closeSheet);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeSheet(); });
  // Swipe a sheet down to dismiss it.
  document.querySelectorAll('.m-sheet').forEach(function (s) {
    var y0 = null;
    s.addEventListener('touchstart', function (e) { y0 = s.scrollTop <= 0 ? e.touches[0].clientY : null; }, { passive: true });
    s.addEventListener('touchmove', function (e) {
      if (y0 === null) return;
      var dy = e.touches[0].clientY - y0;
      if (dy > 0) s.style.transform = 'translateY(' + dy + 'px)';
    }, { passive: true });
    s.addEventListener('touchend', function (e) {
      if (y0 === null) return;
      var dy = e.changedTouches[0].clientY - y0;
      s.style.transform = '';
      if (dy > 80) closeSheet();
      y0 = null;
    });
  });

  // Scope sheet: refill business units when the company changes.
  var tree = document.getElementById('mTenancyTree');
  var co = document.getElementById('mScopeCompany'), bu = document.getElementById('mScopeVertical');
  if (tree && co && bu) {
    var data = JSON.parse(tree.textContent);
    co.addEventListener('change', function () {
      bu.innerHTML = '<option value="all">All business units</option>';
      ((data[co.value] || {}).verticals || []).forEach(function (v) {
        var o = document.createElement('option'); o.value = v.id; o.textContent = v.name; bu.appendChild(o);
      });
    });
  }

  // ---- Tap-to-confirm: the first tap arms the button, the second submits ----
  document.querySelectorAll('button[data-confirm]').forEach(function (btn) {
    var label = btn.innerHTML, timer = null;
    btn.addEventListener('click', function (e) {
      if (btn.classList.contains('armed')) {
        btn.disabled = true;               // stops a double submit; the form still posts
        btn.form && btn.form.requestSubmit ? btn.form.requestSubmit() : btn.form.submit();
        e.preventDefault();
        return;
      }
      e.preventDefault();
      btn.classList.add('armed');
      btn.textContent = btn.dataset.confirm;
      if (navigator.vibrate) navigator.vibrate(10);
      timer = setTimeout(function () { btn.classList.remove('armed'); btn.innerHTML = label; }, 3500);
    });
  });

  // ---- Toasts fade out on their own ----
  var toasts = document.querySelectorAll('.m-toast');
  toasts.forEach(function (t, i) {
    setTimeout(function () { t.classList.add('gone'); setTimeout(function () { t.remove(); }, 400); }, 4200 + i * 600);
    t.addEventListener('click', function () { t.classList.add('gone'); });
  });

  // ---- Navigation progress bar ----
  var bar = document.getElementById('mProgress');
  function go() { if (bar) { bar.classList.remove('go'); void bar.offsetWidth; bar.classList.add('go'); } }
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('data-no-progress')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || (a.origin && a.origin !== location.origin)) return;
    go();
  });
  document.addEventListener('submit', function (e) { setTimeout(function () { if (!e.defaultPrevented) go(); }, 0); });
  window.addEventListener('pageshow', function () { if (bar) bar.classList.remove('go'); });

  // ---- Forecast chart: per-month stacked actual / trend / project value vs budget ----
  var charts = [];
  function money(v) {
    var a = Math.abs(v);
    if (a >= 1e9) return '$' + (a / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
    if (a >= 1e6) return '$' + (a / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (a >= 1e3) return '$' + Math.round(a / 1e3) + 'K';
    return '$' + Math.round(a);
  }
  function css(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }
  function draw(el, d) {
    var W = el.clientWidth, H = el.clientHeight;
    if (!W || !H) return;
    var padL = 40, padB = 20, padT = 6, n = d.labels.length;
    var cw = (W - padL) / n, bw = Math.max(6, Math.min(26, cw * 0.56));
    var tops = d.labels.map(function (_, i) {
      var a = d.actual[i] || 0, f = d.forecast_base[i] || 0, p = d.project_value_add[i] || 0;
      // Current month: actual-to-date sits inside the trend total, so stack trend - actual.
      return Math.max(d.budget[i] || 0, (f ? Math.max(f, a) : a) + p);
    });
    var max = Math.max.apply(null, tops.concat([1])) * 1.08;
    var y = function (v) { return padT + (H - padT - padB) * (1 - v / max); };
    var cA = css('--seg-actual'), cF = css('--seg-forecast'), cP = css('--seg-projects'), cB = css('--text'), cG = css('--border');
    var s = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img">';
    [0, 0.5, 1].forEach(function (t) {
      var v = max / 1.08 * t, yy = Math.round(y(v)) + 0.5;
      s += '<line x1="' + padL + '" x2="' + W + '" y1="' + yy + '" y2="' + yy + '" stroke="' + cG + '" stroke-width="1"/>';
      s += '<text x="' + (padL - 6) + '" y="' + (yy + 4) + '" text-anchor="end">' + money(v) + '</text>';
    });
    d.labels.forEach(function (lab, i) {
      var cx = padL + cw * i + cw / 2, x = cx - bw / 2;
      var a = d.actual[i] || 0, f = d.forecast_base[i] || 0, p = d.project_value_add[i] || 0;
      var segs = [];
      if (f) { segs.push([Math.min(a, f), cA]); segs.push([Math.max(0, f - a), cF]); }
      else segs.push([a, cA]);
      segs.push([p, cP]);
      var base = 0;
      segs.forEach(function (sg, k) {
        if (!(sg[0] > 0)) return;
        var y1 = y(base + sg[0]), y0 = y(base);
        var r = (k === segs.length - 1 || base + sg[0] >= tops[i]) ? 3 : 0;
        s += '<rect x="' + x.toFixed(1) + '" y="' + y1.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + Math.max(0.5, y0 - y1).toFixed(1) + '" fill="' + sg[1] + '" rx="' + (r ? 2 : 0) + '"/>';
        base += sg[0];
      });
      if (d.budget[i]) {
        var by = Math.round(y(d.budget[i])) + 0.5;
        s += '<line x1="' + (x - 3).toFixed(1) + '" x2="' + (x + bw + 3).toFixed(1) + '" y1="' + by + '" y2="' + by + '" stroke="' + cB + '" stroke-width="2" stroke-linecap="round"/>';
      }
      if (n <= 6 || i % 2 === 0) s += '<text x="' + cx.toFixed(1) + '" y="' + (H - 4) + '" text-anchor="middle">' + lab + '</text>';
    });
    el.innerHTML = s + '</svg>';
  }
  window.kbChart = function (id, data) {
    var el = document.getElementById(id);
    if (!el || !data) return;
    charts.push([el, data]);
    draw(el, data);
  };
  window.kbRedrawCharts = function () { charts.forEach(function (c) { draw(c[0], c[1]); }); };
  var rt = null;
  window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(window.kbRedrawCharts, 120); });
})();
