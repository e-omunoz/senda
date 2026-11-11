/* Senda — JS de la web (vanilla, sin dependencias). Tema, menú, copiar y búsqueda. */
(function () {
  "use strict";
  var doc = document.documentElement;
  var ROOT = doc.getAttribute("data-root") || "./";

  /* ------------------------------------------------------------ tema */
  var themeBtn = document.getElementById("theme-toggle");
  function syncThemeBtn() {
    if (!themeBtn) return;
    var light = doc.getAttribute("data-theme") === "light";
    themeBtn.setAttribute("aria-label", light ? "Cambiar a tema oscuro" : "Cambiar a tema claro");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", light ? "#f6f2e8" : "#14161b");
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = doc.getAttribute("data-theme") === "light" ? "dark" : "light";
      doc.setAttribute("data-theme", next);
      try { localStorage.setItem("senda-theme", next); } catch (e) { /* sin almacenamiento */ }
      syncThemeBtn();
    });
  }
  syncThemeBtn();
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: light)");
    var onChange = function (e) {
      var stored = null;
      try { stored = localStorage.getItem("senda-theme"); } catch (err) { /* nada */ }
      if (stored) return;
      doc.setAttribute("data-theme", e.matches ? "light" : "dark");
      syncThemeBtn();
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
  }

  /* ------------------------------------------------------------ menú lateral (móvil) */
  var navBtn = document.getElementById("nav-toggle");
  var scrim = document.getElementById("scrim");
  var sidebar = document.getElementById("sidebar");
  function setNav(open) {
    document.body.classList.toggle("nav-open", open);
    if (navBtn) {
      navBtn.setAttribute("aria-expanded", open ? "true" : "false");
      navBtn.setAttribute("aria-label", open ? "Cerrar menú" : "Abrir menú");
    }
    if (scrim) scrim.hidden = !open;
    if (open && sidebar) {
      var first = sidebar.querySelector("a");
      if (first) first.focus();
    }
  }
  if (navBtn) navBtn.addEventListener("click", function () { setNav(!document.body.classList.contains("nav-open")); });
  if (scrim) scrim.addEventListener("click", function () { setNav(false); });
  if (sidebar) sidebar.addEventListener("click", function (e) { if (e.target.closest("a")) setNav(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.body.classList.contains("nav-open")) { setNav(false); if (navBtn) navBtn.focus(); }
  });

  /* ------------------------------------------------------------ copiar */
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy") ? resolve() : reject(); } catch (e) { reject(e); }
      document.body.removeChild(ta);
    });
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-target],[data-copy-text]");
    if (!btn) return;
    var text = btn.getAttribute("data-copy-text");
    if (text === null) {
      var el = document.getElementById(btn.getAttribute("data-copy-target"));
      text = el ? el.textContent : "";
    }
    var label = btn.querySelector("span:not(.sr-only)");
    var old = label ? label.textContent : null;
    copyText(text).then(function () {
      btn.classList.add("copied");
      if (label) label.textContent = "Copiado";
      announce("Copiado al portapapeles");
      setTimeout(function () { btn.classList.remove("copied"); if (label) label.textContent = old; }, 1600);
    }, function () {
      if (label) label.textContent = "Selecciona y copia";
    });
  });

  /* ------------------------------------------------------------ búsqueda */
  var input = document.getElementById("search-input");
  var list = document.getElementById("search-results");
  var status = document.getElementById("search-status");
  var index = null, loading = null, active = -1, results = [];

  function announce(msg) { if (status) status.textContent = msg; }
  function norm(s) {
    return (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function highlight(text, terms) {
    var out = escapeHtml(text);
    var n = norm(text);
    // marca la primera aparición de cada término (sobre el texto original, misma longitud tras normalizar)
    if (n.length !== text.length) return out;
    var marks = [];
    terms.forEach(function (t) {
      var i = n.indexOf(t);
      if (i >= 0) marks.push([i, i + t.length]);
    });
    if (!marks.length) return out;
    marks.sort(function (a, b) { return a[0] - b[0]; });
    var res = "", pos = 0;
    marks.forEach(function (m) {
      if (m[0] < pos) return;
      res += escapeHtml(text.slice(pos, m[0])) + "<mark>" + escapeHtml(text.slice(m[0], m[1])) + "</mark>";
      pos = m[1];
    });
    return res + escapeHtml(text.slice(pos));
  }
  function load() {
    if (index) return Promise.resolve(index);
    if (loading) return loading;
    loading = fetch(ROOT + "search.json").then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (data) {
      index = data.map(function (e) {
        return { e: e, t: norm(e.t), h: norm([e.t, e.c, e.x, e.k].join(" ")) };
      });
      return index;
    });
    return loading;
  }
  function search(q) {
    var terms = norm(q).split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    var out = [];
    for (var i = 0; i < index.length; i++) {
      var it = index[i], score = 0, ok = true;
      for (var j = 0; j < terms.length; j++) {
        var t = terms[j];
        if (it.h.indexOf(t) < 0) { ok = false; break; }
        var ti = it.t.indexOf(t);
        if (ti === 0) score += 6; else if (ti > 0) score += 3; else score += 1;
      }
      if (!ok) continue;
      var k = it.e.k;
      if (k === "Guía" || k === "Clase") score += 4;
      else if (k === "Sección" || k === "Conocimiento" || k === "Macro") score += 2;
      out.push({ s: score - it.t.length / 400, it: it });
    }
    out.sort(function (a, b) { return b.s - a.s; });
    return out.slice(0, 15).map(function (x) { return x.it.e; });
  }
  function render(q) {
    var terms = norm(q).split(/\s+/).filter(Boolean);
    results = search(q);
    active = -1;
    if (!q.trim()) { close(); return; }
    if (!results.length) {
      list.innerHTML = '<li class="sr-empty" role="option" aria-disabled="true">Sin resultados para «' + escapeHtml(q) + "»</li>";
      announce("Sin resultados");
    } else {
      list.innerHTML = results.map(function (e, i) {
        return '<li role="presentation"><a id="sr-' + i + '" role="option" aria-selected="false" href="' + escapeHtml(ROOT + e.u) + '">' +
          '<span class="sr-kind">' + escapeHtml(e.k) + "</span>" + highlight(e.t, terms) +
          (e.c ? '<span class="sr-ctx">' + escapeHtml(e.c) + "</span>" : "") +
          (e.x ? '<span class="sr-text">' + highlight(e.x, terms) + "</span>" : "") + "</a></li>";
      }).join("");
      announce(results.length + (results.length === 1 ? " resultado" : " resultados"));
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }
  function close() {
    if (!list) return;
    list.hidden = true;
    list.innerHTML = "";
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }
  function move(d) {
    var opts = list.querySelectorAll("a[role=option]");
    if (!opts.length) return;
    if (active >= 0) opts[active].setAttribute("aria-selected", "false");
    active = (active + d + opts.length) % opts.length;
    opts[active].setAttribute("aria-selected", "true");
    opts[active].scrollIntoView({ block: "nearest" });
    input.setAttribute("aria-activedescendant", opts[active].id);
  }
  if (input && list) {
    var timer = null;
    input.addEventListener("focus", function () { load().catch(function () {}); });
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value;
      timer = setTimeout(function () {
        load().then(function () { render(q); }, function () {
          list.innerHTML = '<li class="sr-empty">La búsqueda necesita abrir la web desde un servidor.</li>';
          list.hidden = false;
        });
      }, 80);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") {
        var opts = list.querySelectorAll("a[role=option]");
        var target = opts[active >= 0 ? active : 0];
        if (target) { e.preventDefault(); close(); window.location.href = target.href; }
      } else if (e.key === "Escape") { input.value = ""; close(); }
    });
    list.addEventListener("click", function (e) { if (e.target.closest("a")) close(); });
    document.addEventListener("click", function (e) { if (!e.target.closest(".search")) close(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        input.focus();
      }
    });
  }
})();
