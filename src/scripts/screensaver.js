// Hidden /screensaver page: asks for full screen. Browsers only allow that after a user gesture, so it tries on
// load (works where the browser permits it) and again on the first click or key press, then stops asking.
(function () {
  "use strict";
  var root = document.documentElement;
  function request() {
    if (document.fullscreenElement || !root.requestFullscreen) { return; }
    try {
      var result = root.requestFullscreen({ navigationUI: "hide" });
      if (result && result.catch) { result.catch(function () {}); }
    } catch (error) { /* not allowed without a gesture; the next one tries again */ }
  }
  function onGesture() {
    request();
    if (document.fullscreenElement) {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    }
  }
  window.addEventListener("pointerdown", onGesture);
  window.addEventListener("keydown", onGesture);
  request();
})();
