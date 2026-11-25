(function () {
  'use strict';
  // Ask before deleting
  document.addEventListener('submit', function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) e.preventDefault();
  });
  // Preview a chosen file before saving
  document.addEventListener('change', function (e) {
    var inp = e.target, kind = inp.getAttribute && inp.getAttribute('data-preview');
    if (!kind || !inp.files || !inp.files[0]) return;
    var box = inp.parentNode.querySelector('.newprev');
    if (!box) return;
    var url = URL.createObjectURL(inp.files[0]);
    box.innerHTML = '';
    var el = document.createElement(kind === 'image' ? 'img' : 'video');
    el.className = 'prev'; el.src = url;
    if (kind === 'video') { el.controls = true; el.muted = true; el.preload = 'metadata'; }
    box.appendChild(el);
  });
  // Show an "uploading" note while a form with files is sent
  var up = document.querySelector('form[data-upload]');
  if (up) up.addEventListener('submit', function () {
    var n = up.querySelector('.upl-note');
    if (n) n.hidden = false;
    var b = up.querySelector('button[type=submit]');
    if (b) setTimeout(function () { b.disabled = true; }, 0);
  });
})();
