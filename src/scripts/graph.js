/*
 * Knowledge graph page: a topic opens without the jump of the fragment, the URL keeps the history,
 * the study trail is marked on the canvas with its order, and the focus follows the topic.
 * Without this script the page works by the fragment alone (see graph.css).
 * Nothing is stored in the browser: nodeState() is the extension point for the next version.
 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var BADGE_RADIUS = 9;
  var ARROW_STEPS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
  var graph = document.querySelector("[data-graph]");
  if (!graph) { return; }

  // The link that opened the open topic: Esc gives the focus back to it.
  var opener = null;

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

  // The trail is read from the list of the topic: its order is the order of the badges.
  function markTrail(topic) {
    clearTrail();
    var steps = topic.querySelectorAll("ol[data-trail] > li");
    var nodes = nodeLinks();
    for (var i = 0; i < steps.length; i++) {
      var link = steps[i].querySelector("a[href^='#']");
      if (!link) { continue; }
      for (var j = 0; j < nodes.length; j++) {
        if (nodes[j].getAttribute("href") === link.getAttribute("href")) {
          nodes[j].setAttribute("data-trail", String(i + 1));
          drawBadge(nodes[j], i + 1);
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
    markTrail(topic);
    if (options.link) { opener = options.link; }
    if (options.push && window.location.hash !== "#" + topic.id) {
      window.history.pushState(null, "", "#" + topic.id);
    }
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

  graph.setAttribute("data-js", "");
  var initial = topicFromHash(window.location.hash);
  if (initial) { open(initial, { push: false, focus: false }); }
})();
