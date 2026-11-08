/* Router: soft page changes on top of real pages. Every URL is still a complete static HTML file, so
   crawlers, direct visits and visitors without script get exactly that. With script, a click on an
   internal link fetches the next page, swaps only <main> (and the menu panel, title and meta), and
   updates the address with the History API. Header, footer and the water canvas are never reloaded, so
   the water keeps running across pages. When anything looks unusual (a page with its own external
   script, a missing <main>, a failed fetch) it falls back to a normal navigation. No libraries. */
(function () {
  if (!window.fetch || !window.history || !history.pushState || !window.DOMParser) { return; }

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  // The one duration of the page transition, read from the same token the stylesheets use
  // (--duration-page in tokens.css), so the content and the water fade together. The header has
  // no background of its own: the page background shows behind it.
  function pageFade() {
    var value = getComputedStyle(document.documentElement).getPropertyValue("--duration-page").trim();
    var match = /^([\d.]+)(ms|s)$/.exec(value);
    if (!match) { return 250; }
    return match[2] === "s" ? parseFloat(match[1]) * 1000 : parseFloat(match[1]);
  }
  var FADE = pageFade(); // ms, each way
  var controller = null;
  var token = 0;
  var shown = location.pathname + location.search; // the page on screen, so a hash-only history step is left to the browser
  try { history.scrollRestoration = "manual"; } catch (error) { /* the browser keeps its own */ }

  // Scripts that are part of the shell. Any other external script belongs to one page and needs a real load.
  function isShell(script) { return /\/scripts\/(water|router)\.js$/.test(script.getAttribute("src")); }
  function hasPageScript(doc) {
    var scripts = doc.querySelectorAll("script[src]");
    for (var i = 0; i < scripts.length; i++) { if (!isShell(scripts[i])) { return true; } }
    return false;
  }
  function hasWater(doc) {
    var scripts = doc.querySelectorAll("script[src]");
    for (var i = 0; i < scripts.length; i++) { if (/\/water\.js$/.test(scripts[i].getAttribute("src"))) { return true; } }
    return false;
  }

  function eligible(link, event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) { return false; }
    if (link.target && link.target !== "_self") { return false; }
    if (link.hasAttribute("download") || link.origin !== location.origin) { return false; }
    if (link.pathname.slice(-1) !== "/") { return false; } // pages end in "/"; feeds and files are real loads
    if (link.pathname === location.pathname && link.search === location.search) { return false; } // same page or its hash
    return true;
  }

  function fade(element, from, to) {
    if (reduced.matches || !element.animate) { return Promise.resolve(); }
    return element.animate([{ opacity: from }, { opacity: to }], { duration: FADE, easing: "ease", fill: "forwards" }).finished.catch(function () {});
  }

  function runScripts(container) {
    var scripts = container.querySelectorAll("script");
    Array.prototype.forEach.call(scripts, function (old) {
      var copy = document.createElement("script");
      copy.textContent = old.textContent;
      old.parentNode.replaceChild(copy, old);
    });
  }

  function syncHead(doc) {
    document.title = doc.title;
    document.documentElement.lang = doc.documentElement.lang;
    ["link[rel=canonical]", "meta[name=description]"].forEach(function (selector) {
      var from = doc.querySelector(selector);
      var to = document.querySelector(selector);
      if (from && to) { to.replaceWith(from.cloneNode(true)); }
    });
    var old = document.head.querySelectorAll("script[type='application/ld+json']");
    Array.prototype.forEach.call(old, function (node) { node.remove(); });
    Array.prototype.forEach.call(doc.querySelectorAll("script[type='application/ld+json']"), function (node) {
      document.head.appendChild(node.cloneNode(true));
    });
  }

  function waterOn(on) {
    document.dispatchEvent(new CustomEvent("water:toggle", { detail: { on: on } }));
  }

  function swap(doc, url, scroll) {
    var main = document.getElementById("main");
    var next = doc.getElementById("main");
    var panel = document.getElementById("menu-panel");
    var nextPanel = doc.getElementById("menu-panel");
    syncHead(doc);
    if (panel && nextPanel) { panel.innerHTML = nextPanel.innerHTML; }
    // Cover pages swap the water background; every page keeps the normal scroll.
    document.body.toggleAttribute("data-cover", doc.body.hasAttribute("data-cover"));
    main.innerHTML = next.innerHTML;
    runScripts(main);
    var wants = hasWater(doc);
    if (wants && !document.querySelector("script[src$='/scripts/water.js']")) {
      var script = document.createElement("script");
      script.src = "/scripts/water.js";
      document.body.appendChild(script);
    } else {
      waterOn(wants);
    }
    var hash = url.hash && document.getElementById(decodeURIComponent(url.hash.slice(1)));
    if (hash) { hash.scrollIntoView(); } else { window.scrollTo(0, scroll || 0); }
    main.focus({ preventScroll: true });
    document.dispatchEvent(new CustomEvent("page:swap"));
  }

  function go(url, push, scroll) {
    var mine = ++token;
    if (controller) { controller.abort(); }
    controller = new AbortController();
    var main = document.getElementById("main");
    var out = fade(main, 1, 0);
    var request = fetch(url.href, { signal: controller.signal, headers: { Accept: "text/html" } }).then(function (response) {
      var type = response.headers.get("content-type") || "";
      if (!response.ok || type.indexOf("text/html") === -1) { throw new Error("not a page"); }
      return response.text();
    });
    Promise.all([request, out]).then(function (results) {
      if (mine !== token) { return; }
      var doc = new DOMParser().parseFromString(results[0], "text/html");
      if (!doc.getElementById("main") || hasPageScript(doc) || !!doc.getElementById("menu-panel") !== !!document.getElementById("menu-panel")) {
        throw new Error("needs a real load");
      }
      if (push) {
        history.replaceState({ y: window.scrollY }, "");
        history.pushState({ y: 0 }, "", url.href);
      }
      swap(doc, url, scroll);
      shown = url.pathname + url.search;
      return fade(main, 0, 1).then(function () { if (main.getAnimations) { main.getAnimations().forEach(function (a) { a.cancel(); }); } });
    }).catch(function (error) {
      if (error && error.name === "AbortError") { return; }
      if (mine === token) { location.assign(url.href); }
    });
  }

  // The first page was a real load: stop here when it has its own script, which this swap could not clean up.
  if (hasPageScript(document)) { return; }

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[href]");
    if (!link || !eligible(link, event)) { return; }
    event.preventDefault();
    var url = new URL(link.href);
    if (url.pathname === location.pathname && url.search === location.search) { return; }
    go(url, true, 0);
  });

  window.addEventListener("popstate", function (event) {
    if (location.pathname + location.search === shown) { return; }
    go(new URL(location.href), false, event.state && event.state.y);
  });
})();
