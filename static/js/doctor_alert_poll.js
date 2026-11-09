/* Included on every doctor page. Polls /doctor/alerts/feed, keeps the sidebar badge current,
   and shows a pop-up when a patient needs attention: loud for help/emergency, quiet (no sound)
   for the automatic "possible distress" guess. Self-contained (injects its own CSS). */
(function () {
  if (window.__sukhamAlertPoll) return;
  window.__sukhamAlertPoll = true;

  var POLL_MS = 5000, BEEP_KEY = 'sukham_last_alert_beep', DISMISS_KEY = 'sukham_dismissed_alerts';
  var audio = null, toastId = null;

  var style = document.createElement('style');
  style.textContent =
    '.sukham-toast{position:fixed;right:18px;bottom:18px;z-index:9999;max-width:340px;padding:14px 34px 14px 16px;border-radius:12px;' +
    'color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.35);font-family:inherit}' +
    '.sukham-toast.emergency{background:#c62828}.sukham-toast.help{background:#ef6c00}.sukham-toast.caution{background:#8a5a00}' +
    '.sukham-toast b{display:block;font-size:1rem;margin-bottom:2px}' +
    '.sukham-toast a{color:#fff;font-weight:700;text-decoration:underline}' +
    '.sukham-toast button{position:absolute;top:6px;right:8px;background:none;border:0;color:#fff;font-size:1.1rem;cursor:pointer}';
  document.head.appendChild(style);

  function loadDismissed() { try { return JSON.parse(sessionStorage.getItem(DISMISS_KEY) || '[]'); } catch (e) { return []; } }
  function saveDismissed(list) { try { sessionStorage.setItem(DISMISS_KEY, JSON.stringify(list.slice(-50))); } catch (e) {} }

  // Browsers only allow sound after the user has interacted with the page once.
  function unlock() {
    try {
      var C = window.AudioContext || window.webkitAudioContext;
      audio = audio || new C();
      if (audio.state === 'suspended') audio.resume();
    } catch (e) {}
  }
  ['pointerdown', 'keydown'].forEach(function (ev) { window.addEventListener(ev, unlock, { once: true }); });

  function beep(level) {
    if (!audio || audio.state !== 'running') return;
    var n = level === 'emergency' ? 4 : 2, freq = level === 'emergency' ? 1200 : 800;
    for (var i = 0; i < n; i++) {
      var o = audio.createOscillator(), g = audio.createGain(), t = audio.currentTime + i * 0.35;
      o.frequency.value = freq; g.gain.value = 0.18;
      o.connect(g); g.connect(audio.destination); o.start(t); o.stop(t + 0.22);
    }
  }

  function removeToast() { var t = document.getElementById('sukham-toast'); if (t) t.remove(); toastId = null; }

  function showToast(a) {
    if (toastId === a.id && document.getElementById('sukham-toast')) return;   // already showing this one
    removeToast(); toastId = a.id;
    var t = document.createElement('div');
    t.id = 'sukham-toast'; t.className = 'sukham-toast ' + a.level; t.setAttribute('role', 'alert');
    var b = document.createElement('b');
    b.textContent = (a.level === 'caution' ? 'Possible distress (automatic guess): ' : a.label + ': ') + a.patient;
    var s = document.createElement('span');
    s.textContent = 'Signalled at ' + a.time + (a.escalated ? ', no response yet, so every doctor is alerted. ' : '. ');
    var l = document.createElement('a'); l.href = '/doctor/alerts'; l.textContent = 'Open alerts';
    var x = document.createElement('button'); x.textContent = '\u00d7'; x.setAttribute('aria-label', 'Dismiss');
    x.onclick = function () { var d = loadDismissed(); d.push(a.id); saveDismissed(d); removeToast(); };
    t.appendChild(b); t.appendChild(s); t.appendChild(l); t.appendChild(x);
    document.body.appendChild(t);
  }

  function handle(d) {
    document.querySelectorAll('[data-alert-badge]').forEach(function (el) { el.textContent = d.open; el.hidden = !d.open; });
    window.dispatchEvent(new CustomEvent('sukham:alerts', { detail: d }));

    var dismissed = loadDismissed();
    var a = [d.latest_urgent, d.latest_notice].filter(function (x) { return x && dismissed.indexOf(x.id) < 0; })[0];
    if (!a) { removeToast(); return; }
    showToast(a);

    if (a.level !== 'caution') {                       // only help / emergency make a sound
      var last = 0;
      try { last = parseInt(sessionStorage.getItem(BEEP_KEY) || '0', 10); } catch (e) {}
      if (a.id > last) {
        beep(a.level);
        try { sessionStorage.setItem(BEEP_KEY, String(a.id)); } catch (e) {}
      }
    }
  }

  function poll() {
    fetch('/doctor/alerts/feed', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { if (!r.ok || r.redirected) throw 0; return r.json(); })
      .then(handle)
      .catch(function () {})
      .then(function () { setTimeout(poll, POLL_MS); });
  }
  poll();
})();
