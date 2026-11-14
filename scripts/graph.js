/*
 * Knowledge graph page: a topic opens without the jump of the fragment, the URL keeps the history,
 * the study trail is marked on the canvas with its order, and the focus follows the topic.
 * On a touch screen one finger pans the canvas and two fingers zoom it; the open topic's node is
 * scrolled above the bottom sheet. Without this script the page works by the fragment alone (see graph.css).
 * Nothing is stored in the browser: nodeState() is the extension point for the next version.
 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var BADGE_RADIUS = 9;
  var MAX_ZOOM = 3;
  var ARROW_STEPS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
  var graph = document.querySelector("[data-graph]");
  if (!graph) { return; }

  var canvas = graph.querySelector("[data-canvas]");
  var canvasWrap = graph.querySelector("[data-canvas-wrap]");
  var baseWidth = canvas ? Number(canvas.getAttribute("width")) : 0;
  var baseHeight = canvas ? Number(canvas.getAttribute("height")) : 0;
  var zoom = 1;

  // The touch pointers on the canvas (id to last position) and the distance between two of them.
  var touches = {};
  var pinchDistance = 0;

  // The link that opened the open topic: Esc gives the focus back to it.
  var opener = null;

  // The trail filter: "strong" shows only the required steps, "all" every step. Kept in memory only.
  var trailFilter = graph.querySelector("[data-trail-filter]");
  var trailMode = "all";

  // Extension point of the next version (the reader's progress per topic). Nothing is stored yet.
  function nodeState(id) {
    return null;
  }

  function openTopic() {
    return graph.querySelector("article[data-node][data-current]");
  }

  function topicFor(id) {
    var element = document.getElementById(id);
    return element && graph.contains(element) && element.matches("article[data-node]") ? element : null;
  }

  function topicFromHash(hash) {
    var id;
    try { id = decodeURIComponent(hash.slice(1)); } catch (error) { return null; }
    return id ? topicFor(id) : null;
  }

  function linksTo(id) {
    var anchors = graph.querySelectorAll("a");
    var found = [];
    for (var i = 0; i < anchors.length; i++) {
      if (anchors[i].getAttribute("href") === "#" + id) { found.push(anchors[i]); }
    }
    return found;
  }

  function nodeLinks() {
    return Array.prototype.slice.call(graph.querySelectorAll("[data-node-link]"));
  }

  // The box of the topic's node on the canvas, or null when there is none.
  function canvasBox(id) {
    var links = nodeLinks();
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute("href") === "#" + id) { return links[i].querySelector("[data-node-box]"); }
    }
    return null;
  }

  // Below 780 px the open topic is a bottom sheet over the page. Its node must not stay under the
  // sheet: the canvas scrolls sideways to it and the page scrolls down to it, into the space above the sheet.
  function revealNode(topic) {
    var panel = graph.querySelector("[data-panel]");
    var box = canvasBox(topic.id);
    if (!box || !panel || !canvasWrap || canvasWrap.getClientRects().length === 0) { return; }
    if (getComputedStyle(panel).position !== "fixed") { return; }

    var wrap = canvasWrap.getBoundingClientRect();
    var rect = box.getBoundingClientRect();
    if (rect.left < wrap.left || rect.right > wrap.right) {
      canvasWrap.scrollLeft += rect.left + rect.width / 2 - (wrap.left + canvasWrap.clientWidth / 2);
    }
    rect = box.getBoundingClientRect();
    var sheetTop = panel.getBoundingClientRect().top;
    if (rect.top < 0 || rect.bottom > sheetTop) {
      window.scrollBy(0, rect.top + rect.height / 2 - sheetTop / 2);
    }
  }

  // Touch only: one finger pans, and the canvas scrolls by the page's own position for vertical moves.
  function panCanvas(dx, dy) {
    canvasWrap.scrollLeft -= dx;
    window.scrollBy(0, -dy);
  }

  // Zooms to the next factor (between 1 and MAX_ZOOM), keeping the point (x, y) under the fingers.
  function zoomCanvas(next, x, y) {
    next = Math.min(MAX_ZOOM, Math.max(1, next));
    if (next === zoom) { return; }
    var before = canvas.getBoundingClientRect();
    var fx = (x - before.left) / before.width;
    var fy = (y - before.top) / before.height;
    zoom = next;
    canvas.setAttribute("width", String(baseWidth * zoom));
    canvas.setAttribute("height", String(baseHeight * zoom));
    var after = canvas.getBoundingClientRect();
    canvasWrap.scrollLeft += after.left + fx * after.width - x;
    window.scrollBy(0, after.top + fy * after.height - y);
  }

  function touchList() {
    return Object.keys(touches).map(function (id) { return touches[id]; });
  }

  function clearTrail() {
    var marked = graph.querySelectorAll("[data-node-link][data-trail]");
    for (var i = 0; i < marked.length; i++) { marked[i].removeAttribute("data-trail"); }
    var badges = graph.querySelectorAll("[data-trail-badge]");
    for (var j = 0; j < badges.length; j++) { badges[j].remove(); }
  }

  function drawBadge(node, order) {
    var box = node.querySelector("[data-node-box]");
    var x = Number(box.getAttribute("x"));
    var y = Number(box.getAttribute("y"));

    var dot = document.createElementNS(SVG_NS, "circle");
    dot.setAttribute("data-trail-badge", "dot");
    dot.setAttribute("cx", String(x));
    dot.setAttribute("cy", String(y));
    dot.setAttribute("r", String(BADGE_RADIUS));

    var label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("data-trail-badge", "label");
    label.setAttribute("x", String(x));
    label.setAttribute("y", String(y));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("dominant-baseline", "central");
    label.setAttribute("aria-hidden", "true");
    label.textContent = String(order);

    node.appendChild(dot);
    node.appendChild(label);
  }

  // The filter hides the weak steps of the trail (and the whole trail when none is required).
  function applyTrail(topic) {
    var block = topic.querySelector("[data-trail-block]");
    if (!block) { return; }
    var steps = block.querySelectorAll("ol[data-trail] > li");
    var shown = 0;
    for (var i = 0; i < steps.length; i++) {
      if (trailMode === "strong" && steps[i].getAttribute("data-strength") !== "strong") {
        steps[i].setAttribute("hidden", "");
      } else {
        steps[i].removeAttribute("hidden");
        shown++;
      }
    }
    if (shown > 0) { block.removeAttribute("hidden"); } else { block.setAttribute("hidden", ""); }
  }

  // The filter is offered only when the open topic has a trail.
  function showTrailFilter(topic) {
    if (!trailFilter) { return; }
    if (topic.querySelector("[data-trail-block]")) { trailFilter.removeAttribute("hidden"); } else { trailFilter.setAttribute("hidden", ""); }
  }

  // The trail is read from the list of the topic: its order is the order of the badges.
  // Hidden steps get no badge, so the numbers follow the steps that are shown.
  function markTrail(topic) {
    clearTrail();
    var steps = topic.querySelectorAll("ol[data-trail] > li");
    var nodes = nodeLinks();
    var order = 0;
    for (var i = 0; i < steps.length; i++) {
      if (steps[i].hidden) { continue; }
      var link = steps[i].querySelector("a[href^='#']");
      if (!link) { continue; }
      order++;
      for (var j = 0; j < nodes.length; j++) {
        if (nodes[j].getAttribute("href") === link.getAttribute("href")) {
          nodes[j].setAttribute("data-trail", String(order));
          drawBadge(nodes[j], order);
          break;
        }
      }
    }
  }

  function open(topic, options) {
    var current = openTopic();
    if (current && current !== topic) { current.removeAttribute("data-current"); }
    topic.setAttribute("data-current", "");
    var state = nodeState(topic.id);
    if (state !== null) { topic.setAttribute("data-state", state); }
    showTrailFilter(topic);
    applyTrail(topic);
    markTrail(topic);
    if (options.link) { opener = options.link; }
    if (options.push && window.location.hash !== "#" + topic.id) {
      window.history.pushState(null, "", "#" + topic.id);
    }
    revealNode(topic);
    if (options.focus) {
      var title = topic.querySelector("h2");
      title.setAttribute("tabindex", "-1");
      title.focus({ preventScroll: true });
    }
  }

  function close(options) {
    var current = openTopic();
    if (!current) { return; }
    current.removeAttribute("data-current");
    clearTrail();
    if (options.push && window.location.hash) {
      window.history.pushState(null, "", window.location.pathname + window.location.search);
    }
  }

  // The link of the topic that is showing: the one that opened it, else the canvas or the list link.
  function returnFocus(id) {
    var candidates = linksTo(id);
    if (opener && candidates.indexOf(opener) !== -1) { candidates.unshift(opener); }
    for (var i = 0; i < candidates.length; i++) {
      if (candidates[i].getClientRects().length > 0) {
        candidates[i].focus({ preventScroll: true });
        return;
      }
    }
  }

  graph.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) { return; }
    var link = event.target.closest ? event.target.closest("a[href^='#']") : null;
    if (!link || !graph.contains(link)) { return; }
    var topic = topicFromHash(link.getAttribute("href"));
    if (!topic) { return; }
    event.preventDefault();
    open(topic, { push: true, focus: true, link: link });
  });

  graph.addEventListener("keydown", function (event) {
    var step = ARROW_STEPS[event.key];
    if (!step || !event.target.matches || !event.target.matches("[data-node-link]")) { return; }
    var links = nodeLinks();
    var next = links[links.indexOf(event.target) + step];
    if (!next) { return; }
    event.preventDefault();
    next.focus();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") { return; }
    var current = openTopic();
    if (!current) { return; }
    var id = current.id;
    close({ push: true });
    returnFocus(id);
  });

  // Back and forward: the URL decides which topic is open. Focus moves only if it was inside the topic.
  window.addEventListener("popstate", function () {
    var current = openTopic();
    var inside = current !== null && current.contains(document.activeElement);
    var topic = topicFromHash(window.location.hash);
    if (topic) {
      open(topic, { push: false, focus: inside });
    } else {
      close({ push: false });
      if (current && inside) { returnFocus(current.id); }
    }
  });

  // The checked radio is read, not assumed: browsers restore form state on back and reload.
  function checkedTrailMode() {
    var checked = trailFilter ? trailFilter.querySelector("input:checked") : null;
    return checked ? checked.value : "all";
  }

  if (trailFilter) {
    trailFilter.addEventListener("change", function () {
      trailMode = checkedTrailMode();
      var current = openTopic();
      if (current) {
        applyTrail(current);
        markTrail(current);
      }
    });
  }

  if (canvas && canvasWrap) {
    canvasWrap.addEventListener("pointerdown", function (event) {
      if (event.pointerType !== "touch") { return; }
      touches[event.pointerId] = { x: event.clientX, y: event.clientY };
      var active = touchList();
      if (active.length === 2) { pinchDistance = Math.hypot(active[0].x - active[1].x, active[0].y - active[1].y); }
    });

    // Move and release are read on the document: a pointer that leaves the canvas keeps its gesture.
    document.addEventListener("pointermove", function (event) {
      var point = touches[event.pointerId];
      if (!point) { return; }
      var previousX = point.x;
      var previousY = point.y;
      point.x = event.clientX;
      point.y = event.clientY;
      var active = touchList();
      if (active.length === 1) {
        panCanvas(point.x - previousX, point.y - previousY);
      } else if (active.length === 2) {
        var distance = Math.hypot(active[0].x - active[1].x, active[0].y - active[1].y);
        if (pinchDistance > 0 && distance > 0) {
          zoomCanvas(zoom * distance / pinchDistance,
            (active[0].x + active[1].x) / 2, (active[0].y + active[1].y) / 2);
        }
        pinchDistance = distance;
      }
    });

    var release = function (event) {
      if (!touches[event.pointerId]) { return; }
      delete touches[event.pointerId];
      pinchDistance = 0;
    };
    document.addEventListener("pointerup", release);
    document.addEventListener("pointercancel", release);
  }

  graph.setAttribute("data-js", "");
  trailMode = checkedTrailMode();
  var initial = topicFromHash(window.location.hash);
  if (initial) { open(initial, { push: false, focus: false }); }
})();
