(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)); };
  var WA = document.body.getAttribute('data-wa') || '';
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- mobile menu ---------- */
  var tg = $('#tg'), nav = $('#nav');
  var ICON_MENU = '<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
  var ICON_CLOSE = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  function menu(open) {
    nav.classList.toggle('open', open);
    tg.setAttribute('aria-expanded', open);
    tg.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    tg.innerHTML = open ? ICON_CLOSE : ICON_MENU;
  }
  tg.addEventListener('click', function () { menu(!nav.classList.contains('open')); });
  $$('a', nav).forEach(function (a) { a.addEventListener('click', function () { menu(false); }); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') menu(false); });

  /* ---------- header state and scroll progress ---------- */
  var hdr = $('header.top'), bar = $('.progress i'), ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      var y = window.scrollY, h = document.documentElement.scrollHeight - window.innerHeight;
      hdr.classList.toggle('sm', y > 24);
      if (bar) bar.style.transform = 'scaleX(' + (h > 0 ? Math.min(1, y / h) : 0) + ')';
      ticking = false;
    });
  }
  addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* ---------- work: filters, hover preview, modal ---------- */
  var chips = $$('.chip'), its = $$('.it');
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      var f = c.getAttribute('data-f');
      chips.forEach(function (x) { x.setAttribute('aria-pressed', x === c); });
      its.forEach(function (i) { i.hidden = f !== 'all' && i.getAttribute('data-c') !== f; });
    });
  });

  var m = $('#rm'), st = $('#ms');
  function pv() { return '<div class="pv"><div class="bar"><i></i></div></div>'; }
  function go(i) {
    i.classList.add('play');
    var s = i.getAttribute('data-src'), t = $('.th', i);
    if (s && !$('video', t)) {
      var v = document.createElement('video');
      v.src = s; v.muted = true; v.loop = true; v.playsInline = true; v.autoplay = true; v.preload = 'metadata';
      t.insertBefore(v, t.firstChild);
      var p = v.play(); if (p && p.catch) p.catch(function () {});
    }
  }
  function no(i) {
    i.classList.remove('play');
    var v = $('video', i);
    if (v) { v.pause(); v.remove(); }
  }
  function openModal(i) {
    var t = $('.th', i), s = i.getAttribute('data-src'), title = $('h3', i).textContent;
    st.style.setProperty('--c', t.style.getPropertyValue('--c'));
    st.innerHTML = '';
    if (s) {
      var v = document.createElement('video');
      v.src = s; v.autoplay = true; v.loop = true; v.muted = true; v.playsInline = true; v.controls = true;
      st.appendChild(v);
    } else {
      st.innerHTML = '<span class="pb"></span>';
    }
    st.insertAdjacentHTML('beforeend', pv());
    $('#mt').textContent = title;
    $('#mx').textContent = s ? '' : 'Placeholder preview. A real video will play here.';
    $('#mc').href = '/contact?service=' + encodeURIComponent('Reels and videos') +
      '&msg=' + encodeURIComponent('I liked “' + title + '” and want something similar.');
    if (m.showModal) m.showModal();
  }
  its.forEach(function (i) {
    var t = $('.th', i);
    t.insertAdjacentHTML('beforeend', pv());
    t.tabIndex = 0;
    t.setAttribute('role', 'button');
    t.setAttribute('aria-label', 'Preview: ' + $('h3', i).textContent);
    i.addEventListener('mouseenter', function () { go(i); });
    i.addEventListener('mouseleave', function () { no(i); });
    t.addEventListener('focus', function () { go(i); });
    t.addEventListener('blur', function () { no(i); });
    t.addEventListener('click', function () { openModal(i); });
    t.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openModal(i); }
    });
  });
  if (m) {
    m.addEventListener('click', function (e) { if (e.target === m) m.close(); });
    m.addEventListener('close', function () { st.innerHTML = ''; });
    $('#mx2').addEventListener('click', function () { m.close(); });
  }

  /* ---------- review slider ---------- */
  var tr = $('#tr'), dt = $('#dots');
  if (tr && dt) {
    var sl = $$('#tr>figure'), cur = 0, tm;
    var mark = function (i) {
      cur = i;
      $$('button', dt).forEach(function (b, k) { b.setAttribute('aria-current', k === i); });
    };
    var show = function (i) {
      tr.scrollTo({ left: sl[i].offsetLeft - tr.offsetLeft, behavior: reduce ? 'auto' : 'smooth' });
      mark(i);
    };
    var stop = function () { clearInterval(tm); };
    var run = function () {
      stop();
      if (!reduce && sl.length > 1) tm = setInterval(function () { show((cur + 1) % sl.length); }, 4500);
    };
    sl.forEach(function (s, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-label', 'Show review ' + (i + 1));
      b.addEventListener('click', function () { show(i); run(); });
      dt.appendChild(b);
    });
    if (sl.length > 1) {
      tr.addEventListener('scroll', function () {
        var w = sl[1].offsetLeft - sl[0].offsetLeft;
        mark(Math.max(0, Math.min(sl.length - 1, Math.round(tr.scrollLeft / w))));
      });
    } else { dt.hidden = true; }
    ['pointerenter', 'touchstart', 'focusin'].forEach(function (e) { tr.addEventListener(e, stop, { passive: true }); });
    ['pointerleave', 'touchend', 'focusout'].forEach(function (e) { tr.addEventListener(e, run, { passive: true }); });
    mark(0); run();
  }

  /* ---------- enquiry form: validate, save, then offer WhatsApp ---------- */
  var form = $('#startForm');
  if (form) {
    var sent = $('#sent');
    var showErrors = function (errors) {
      $$('[data-err]', form).forEach(function (el) {
        var msg = errors[el.getAttribute('data-err')] || '';
        el.textContent = msg;
        var field = el.previousElementSibling;
        if (field) field.setAttribute('aria-invalid', msg ? 'true' : 'false');
      });
      var first = $$('[aria-invalid="true"]', form)[0];
      if (first) first.focus();
    };
    form.addEventListener('submit', function (e) {
      if (!window.fetch || !window.FormData) return;          // plain form post still works
      e.preventDefault();
      var f = form.elements, errors = {};
      if (f.name.value.trim().length < 2) errors.name = 'Please enter your name.';
      if (!/^\+?[0-9\s-]{10,15}$/.test(f.phone.value.trim())) errors.phone = 'Enter a valid phone number (10 to 15 digits).';
      if (f.message.value.trim().length < 10) errors.message = 'Please tell us a little about your project (at least 10 characters).';
      showErrors(errors);
      if (Object.keys(errors).length) return;
      var btn = $('button[type=submit]', form), label = btn.textContent;
      btn.disabled = true; btn.textContent = 'Sending…';
      fetch(form.action, {
        method: 'POST', body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch', 'X-CSRF-Token': f._csrf.value }
      }).then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); })
        .then(function (res) {
          if (res.body.ok) {
            $('#sentName').textContent = res.body.name;
            var a = $('#sentWa');
            a.href = res.body.wa;
            a.hidden = !res.body.whatsapp;
            form.hidden = true; sent.hidden = false;
            sent.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
            form.reset();
          } else {
            showErrors(res.body.errors || {});
          }
        })
        .catch(function () {
          showErrors({ message: 'Something went wrong. Please try again, or message us on WhatsApp.' });
        })
        .then(function () { btn.disabled = false; btn.textContent = label; });
    });
  }

  /* ---------- reveal on scroll (staggered) ---------- */
  var rv = $$('.rv');
  if ('IntersectionObserver' in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      var batch = entries.filter(function (e) { return e.isIntersecting; });
      batch.forEach(function (e, n) {
        var el = e.target;
        el.style.setProperty('--d', (n * 0.08) + 's');
        el.classList.add('in');
        setTimeout(function () { el.style.removeProperty('--d'); }, 1200);
        io.unobserve(el);
      });
    }, { threshold: 0.1 });
    rv.forEach(function (el) { io.observe(el); });
  } else {
    rv.forEach(function (el) { el.classList.add('in'); });
  }
})();
