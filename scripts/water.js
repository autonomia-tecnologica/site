/* Water: the page background. One fixed canvas behind the content, one WebGL fragment shader, no libraries,
   no textures and no simulation buffers: the surface is a sum of a few traveling waves (the east wind, small
   ripples that drift west) plus ring waves that are computed from a short list of events. The pointer leaves a
   faint wake (like a hand passing through the water) and a click or tap sends a wide wave across the page.
   The big symbol of the home hero is drawn here too, from a texture of its own SVG: it is bent by the same
   waves and lit by the same sun, so it looks like part of the water. The SVG stays in the page as the fallback.
   Light by design: it renders at a small fraction of the window, caps the frame rate, stops while the tab is
   hidden, and draws one still frame when the visitor asks for reduced motion.
   Colors come from the design tokens (--color-*) and are dulled here, so a palette change in tokens.css reaches it.
   Only the presentation pages load this script (the articles and the graph keep the plain gradient, so nothing moves
   behind the reading). Touch screens and narrow windows never start it: they show a frozen frame of the same water
   (the static background in base.css). Without WebGL or script the canvas never appears and that frame stays. */
(function () {
  // Quality ladder: the render budget (the browser smooths the rest, which suits soft water) and the frame rate.
  // It starts at the top and only goes down: if frames come out slow, the next step is taken; past the last
  // step the water gives up and the plain page background comes back, so a weak phone is never worse off.
  var LEVELS = [
    { pixels: 380000, fps: 30 },
    { pixels: 220000, fps: 30 },
    { pixels: 120000, fps: 20 },
    { pixels: 70000, fps: 15 }
  ];
  // The hidden /screensaver page (a background for videos) runs the same water with the symbol centered: one fixed
  // level at about 1080p, no ladder and no giving up, no pointer, and it ignores reduced motion (it is never read, only recorded).
  var SAVER_PAGE = document.documentElement.hasAttribute("data-screensaver");
  if (SAVER_PAGE) { LEVELS = [{ pixels: 2100000, fps: 30 }]; }
  var MAX_SCALE = 1;
  var SLOW = 1.4; // a level is too much when frames take this many times longer than they should
  var WINDOW = 20; // frames measured before judging a level
  var WARM_UP = 8; // frames ignored after a start or a size change (shader compile, new buffers)
  var level = 0;
  var stopped = false;
  var paused = false; // the page on screen has no water (the router swapped to an article, say); the canvas stays mounted
  var DULL = 0.38; // how much of each token color is traded for gray: "purple, but duller"
  var WAKES = 10;
  var CLICKS = 4;
  var WAKE_LIFE = 2.4; // seconds
  var CLICK_LIFE = 6;

  // The ripple groups, slowest first (the slower group is in front and wins): dir x, dir y, size k, speed, slope.
  var WAVES = [
    [-0.99, 0.10, 11, 0.030, 0.070],
    [-0.95, 0.31, 92, 0.032, 0.045],
    [-0.90, -0.43, 51, 0.035, 0.080],
    [0.92, 0.39, 70, 0.040, 0.045],
    [-0.93, 0.37, 24, 0.050, 0.070],
    [-1.00, -0.05, 118, 0.055, 0.040],
    [0.97, -0.24, 41, 0.055, 0.060],
    [-0.97, 0.24, 34, 0.070, 0.100],
    [-0.88, -0.47, 63, 0.085, 0.060],
    [-0.80, 0.60, 77, 0.090, 0.060]
  ];
  var RING_WAKE = [0.17, 0.05, 95, 1.5, 0.0042]; // speed, sigma, k, decay, amplitude
  var RING_CLICK = [0.42, 0.13, 55, 0.5, 0.0105];
  function glsl(n) { return n.toFixed(4); }
  function glslRing(name, count, r) {
    return "  for (int i = 0; i < " + count + "; i++) { g += ring(p, " + name + "[i], " + r.map(glsl).join(", ") + "); }";
  }

  var root = document.documentElement;
  // The one duration of the page transition, read from the same token the stylesheets use
  // (--duration-page in tokens.css): the water fades on the same clock as the content. The header
  // has no background of its own.
  function pageFade() {
    var value = getComputedStyle(root).getPropertyValue("--duration-page").trim();
    var match = /^([\d.]+)(ms|s)$/.exec(value);
    if (!match) { return 250; }
    return match[2] === "s" ? parseFloat(match[1]) * 1000 : parseFloat(match[1]);
  }
  var PAGE_FADE = pageFade(); // ms
  var reduced = SAVER_PAGE ? { matches: false } : window.matchMedia("(prefers-reduced-motion: reduce)");
  var saver = navigator.connection && navigator.connection.saveData; // the visitor asked for less data and power
  if (saver && !SAVER_PAGE) { return; }
  // Phones and other touch screens get the static frame (base.css): the shader is heavy for them and can
  // give up without notice. The screensaver page keeps the shader, because it is recorded.
  var touch = window.matchMedia("(pointer: coarse)").matches;
  var narrow = window.matchMedia("(max-width: 780px)").matches;
  if (!SAVER_PAGE && (touch || narrow)) { return; }
  var canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  var gl = canvas.getContext("webgl", { antialias: false, alpha: false, depth: false, stencil: false, powerPreference: "low-power" });
  if (!gl) { return; }
  var high = gl.getShaderPrecisionFormat && gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER, gl.HIGH_FLOAT);
  if (high && high.precision === 0) { return; } // only half precision: the waves would jitter as the clock grows

  var VERTEX = "attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }";
  var FRAGMENT = [
    "#ifdef GL_FRAGMENT_PRECISION_HIGH",
    "precision highp float;",
    "#else",
    "precision mediump float;",
    "#endif",
    "uniform vec2 res; uniform float time;",
    "uniform vec4 wake[" + WAKES + "]; uniform vec4 click[" + CLICKS + "];", // x, y, age (negative: unused), amplitude
    "uniform vec3 cBg, cGlow, cTint, cShade, cPale, cMark; uniform vec2 glowAt;",
    "uniform sampler2D sym; uniform float symOn, symSize, symRot, symAlpha; uniform vec2 symC, clipLo, clipHi;",
    "",
    "// One group of small ripples traveling along a fixed direction: its slope at p (the height itself is never",
    "// needed). The group is a short patch (it fades in along and across the travel direction) that moves at half the",
    "// pace of its crests. The ripples never vanish (the water is never bare): they swell inside their group. `taken`",
    "// is how much of the surface a slower group already holds: a group that catches up from behind is damped where",
    "// it overlaps one ahead of it, and the one in front stays at full strength.",
    "vec2 ripples(vec2 p, vec2 dir, float k, float speed, float slope, float t, float seed, inout float taken) {",
    "  float along = dot(dir, p) - 0.5 * speed * t;",
    "  float across = dir.x * p.y - dir.y * p.x;",
    "  float group = smoothstep(-0.05, 0.60, sin(along * (5.0 + seed * 0.7) + seed * 2.3) * sin(across * (7.5 + seed * 0.9) + seed * 4.1));",
    "  float here = 0.42 + 0.58 * group * (1.0 - taken);",
    "  taken = max(taken, group);",
    "  return 1.3 * slope * here * cos(k * dot(dir, p) - k * speed * t) * dir;",
    "}",
    "",
    "// A ring wave packet that leaves the point and spreads: the slope at p.",
    "vec2 ring(vec2 p, vec4 r, float speed, float sigma, float k, float decay, float amp) {",
    "  if (r.z < 0.0) { return vec2(0.0); }",
    "  vec2 d = p - r.xy;",
    "  float rad = length(d) + 0.0001;",
    "  float x = rad - speed * r.z;",
    "  float env = exp(-x * x / (sigma * sigma));",
    "  float fade = r.w * amp * exp(-r.z * decay) * smoothstep(0.0, 0.18, r.z) / (1.0 + rad * 3.5);",
    "  float slope = fade * env * (-2.0 * x / (sigma * sigma) * cos(k * x) - k * sin(k * x));",
    "  return slope * d / rad;",
    "}",
    "",
    "void main() {",
    "  float m = min(res.x, res.y);",
    "  vec2 p = (gl_FragCoord.xy - 0.5 * res) / m;",
    "  float t = time;",
    "  // the surface is never perfectly regular",
    "  // the surface is never perfectly regular",
    "  vec2 q = p + 0.014 * vec2(sin(p.y * 9.0 + t * 0.30), cos(p.x * 8.0 - t * 0.25));",
    "  // wind from the east: the ripples travel west, each group with its own size and its own pace; two come back",
    "  // toward the east. Slowest first, because the slower group is the one in front and it wins.",
    "  float taken = 0.0;",
    "  vec2 g = vec2(0.0);",
    WAVES.map(function (w, i) {
      return "  g += ripples(q, vec2(" + glsl(w[0]) + ", " + glsl(w[1]) + "), " + glsl(w[2]) + ", " + glsl(w[3]) + ", " + glsl(w[4]) + ", t, " + glsl(i + 1) + ", taken);";
    }).join("\n"),
    "  // the pointer's wake and the click waves",
    glslRing("wake", WAKES, RING_WAKE),
    glslRing("click", CLICKS, RING_CLICK),
    "  // light: a soft low sun, so slopes facing it brighten and the others fall into shade",
    "  vec3 n = normalize(vec3(-g * 1.6, 1.0));",
    "  vec3 l = normalize(vec3(-0.40, 0.50, 0.77));",
    "  float diffuse = dot(n, l) - l.z;",
    "  float glint = pow(max(dot(n, normalize(l + vec3(0.0, 0.0, 1.0))), 0.0), 70.0);",
    "  // the same glow as the page, behind where the symbol sits",
    "  vec2 c = glowAt * res / m;",
    "  float d = length(p - c) / (0.30 * res.x / m);",
    "  vec3 col = mix(cBg, cGlow, exp(-d * d * 1.6));",
    "  col = mix(col, cTint, clamp(diffuse * 3.0, 0.0, 1.0) * 0.22);",
    "  col = mix(col, cShade, clamp(-diffuse * 3.0, 0.0, 1.0) * 0.70);",
    "  col = mix(col, cPale, clamp(glint, 0.0, 1.0) * 0.08);",
    "  if (symOn > 0.5) {",
    "    // the symbol sits under the water: the waves bend what we see of it, and light it",
    "    vec2 o = p - symC + vec2(g.x, -g.y) * 0.022 * vec2(1.0, -1.0);",
    "    vec2 s = vec2(o.x, -o.y);",
    "    vec2 loc = vec2(cos(symRot) * s.x + sin(symRot) * s.y, -sin(symRot) * s.x + cos(symRot) * s.y);",
    "    vec2 uv = loc / (symSize * 1.25) + 0.5;",
    "    vec2 inside = step(clipLo, p) * step(p, clipHi);",
    "    // antialiasing: four taps spread inside this pixel (rotated grid), averaged, so the edge has no stair steps",
    "    float px = 1.0 / (m * symSize * 1.25);",
    "    float cover = texture2D(sym, uv + px * vec2(0.125, 0.375)).a + texture2D(sym, uv + px * vec2(-0.375, 0.125)).a",
    "                + texture2D(sym, uv + px * vec2(-0.125, -0.375)).a + texture2D(sym, uv + px * vec2(0.375, -0.125)).a;",
    "    float a = 0.25 * cover * inside.x * inside.y * step(0.0, min(uv.x, uv.y)) * step(max(uv.x, uv.y), 1.0) * symAlpha;",
    "    vec3 mark = cMark * (1.0 + diffuse * 2.2);",
    "    mark = mix(mark, cPale, clamp(glint, 0.0, 1.0) * 0.30);",
    "    col = mix(col, mark, a);",
    "  }",
    "  col += (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 160.0; // dither: no banding",
    "  gl_FragColor = vec4(col, 1.0);",
    "}"
  ].join("\n");

  function compile(type, source) {
    var shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return shader;
  }
  var program = gl.createProgram();
  gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) { return; }
  gl.useProgram(program);

  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var position = gl.getAttribLocation(program, "p");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  var uniform = {};
  ["res", "time", "wake", "click", "cBg", "cGlow", "cTint", "cShade", "cPale", "cMark", "sym", "symOn", "symSize", "symRot", "symAlpha", "symC", "clipLo", "clipHi", "glowAt"].forEach(function (name) {
    uniform[name] = gl.getUniformLocation(program, name);
  });

  gl.uniform2f(uniform.glowAt, SAVER_PAGE ? 0 : 0.24, SAVER_PAGE ? 0 : -0.20); // where the page glow sits: behind the symbol

  // ---- Colors: read from the tokens, dulled toward their own gray. ----
  function token(name) {
    var hex = getComputedStyle(root).getPropertyValue(name).trim().replace("#", "");
    if (hex.length === 3) { hex = hex.replace(/./g, "$&$&"); }
    var n = parseInt(hex, 16);
    if (isNaN(n)) { return null; }
    return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255];
  }
  function dull(rgb, amount) {
    var gray = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
    return rgb.map(function (v) { return v + (gray - v) * amount; });
  }
  function scale(rgb, by) { return rgb.map(function (v) { return v * by; }); }
  var lastScheme = "";
  function applyColors() {
    var bg = token("--color-bg");
    var glow = token("--color-bg-glow");
    var accent = token("--color-accent");
    var pale = token("--color-dep-strong");
    if (!bg || !glow || !accent || !pale) { return; }
    var scheme = bg.join() + glow.join();
    if (scheme === lastScheme) { return; }
    lastScheme = scheme;
    bg = dull(bg, DULL * 0.5);
    glow = dull(glow, DULL);
    gl.uniform3fv(uniform.cBg, bg);
    gl.uniform3fv(uniform.cGlow, glow);
    gl.uniform3fv(uniform.cTint, dull(accent, DULL));
    gl.uniform3fv(uniform.cShade, scale(bg, 0.35));
    gl.uniform3fv(uniform.cPale, dull(pale, DULL));
    gl.uniform3fv(uniform.cMark, dull(accent, DULL * 0.45));
    dirty = true;
  }

  // ---- Size: a small fraction of the window, within a pixel budget. ----
  var dirty = true;
  function resize() {
    var cssWidth = Math.max(1, canvas.clientWidth);
    var cssHeight = Math.max(1, canvas.clientHeight);
    var factor = Math.min(MAX_SCALE, Math.sqrt(LEVELS[level].pixels / (cssWidth * cssHeight)));
    var width = Math.max(2, Math.round(cssWidth * factor));
    var height = Math.max(2, Math.round(cssHeight * factor));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
      gl.uniform2f(uniform.res, width, height);
      dirty = true;
    }
  }

  // ---- Events: the pointer's wake and the click waves, as short ring buffers. ----
  var wakes = new Float32Array(WAKES * 4);
  var wakeBorn = new Float64Array(WAKES).fill(-1e9);
  var clicks = new Float32Array(CLICKS * 4);
  var clickBorn = new Float64Array(CLICKS).fill(-1e9);
  var nextWake = 0;
  var nextClick = 0;
  var started = performance.now();
  function seconds() { return (performance.now() - started) / 1000; }
  function place(event) {
    var m = Math.min(canvas.clientWidth, canvas.clientHeight);
    return [(event.clientX - canvas.clientWidth / 2) / m, (canvas.clientHeight / 2 - event.clientY) / m];
  }
  var last = null; // the pointer's last wake: {x, y, at}
  function onMove(event) {
    if (SAVER_PAGE || stopped || reduced.matches) { return; }
    var at = seconds();
    var point = place(event);
    if (last) {
      var distance = Math.hypot(point[0] - last.x, point[1] - last.y);
      if (distance < 0.03) { return; }
      var speed = distance / Math.max(0.016, at - last.at);
      var amp = Math.min(1, 0.25 + speed * 0.35);
      wakes.set([point[0], point[1], 0, amp], nextWake * 4);
      wakeBorn[nextWake] = at;
      nextWake = (nextWake + 1) % WAKES;
    }
    last = { x: point[0], y: point[1], at: at };
  }
  function onDown(event) {
    if (SAVER_PAGE || stopped || reduced.matches) { return; }
    var point = place(event);
    clicks.set([point[0], point[1], 0, 1], nextClick * 4);
    clickBorn[nextClick] = seconds();
    nextClick = (nextClick + 1) % CLICKS;
  }
  function age(buffer, born, life, now) {
    var any = false;
    for (var i = 0; i < born.length; i++) {
      var old = now - born[i];
      if (old > life) { buffer[i * 4 + 2] = -1; } else { buffer[i * 4 + 2] = old; any = true; }
    }
    return any;
  }

  // ---- The hero symbol: its SVG, drawn once into a texture, placed every frame from where it is on the page. ----
  var mark = document.querySelector(".hero__symbol");
  var markReady = false;
  var texture = null;
  var MARK_FADE = PAGE_FADE / 1000; // seconds the symbol takes to appear when the water was already on (the page-transition time)
  var fadeNext = false;
  var markBorn = -1e9;
  function useMark() {
    markBorn = fadeNext && !reduced.matches ? seconds() : -1e9;
    fadeNext = false;
    markReady = true;
    root.setAttribute("data-water-mark", ""); // hides the SVG: the canvas draws it now
    dirty = true;
    if (reduced.matches) { draw(); }
  }
  function loadMark() {
    if (!mark) { return; }
    if (texture) { useMark(); return; } // the router brought the home page back: the texture is still good
    var copy = mark.cloneNode(true);
    copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    copy.setAttribute("width", "1024");
    copy.setAttribute("height", "1024");
    copy.setAttribute("style", "color:#fff");
    var image = new Image();
    image.onload = function () {
      try {
        var flat = document.createElement("canvas");
        flat.width = 1024;
        flat.height = 1024;
        flat.getContext("2d").drawImage(image, 102, 102, 820, 820);
        texture = gl.createTexture();
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, flat);
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.uniform1i(uniform.sym, 0);
        useMark();
      } catch (error) { /* a browser that taints the canvas: the plain SVG stays */ }
    };
    image.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(copy));
  }
  function placeMark() {
    var m = Math.min(canvas.clientWidth, canvas.clientHeight);
    function px(x, y) { return [(x - canvas.clientWidth / 2) / m, (canvas.clientHeight / 2 - y) / m]; }
    var rect = mark.getBoundingClientRect();
    var style = getComputedStyle(mark);
    var matrix = /matrix\(([^)]+)\)/.exec(style.transform);
    var angle = 0;
    if (matrix) { var v = matrix[1].split(","); angle = Math.atan2(parseFloat(v[1]), parseFloat(v[0])); }
    var center = px(rect.left + rect.width / 2, rect.top + rect.height / 2);
    var clip = (mark.parentElement || mark).getBoundingClientRect(); // the hero cuts the symbol at its edges
    var lo = px(clip.left, clip.bottom);
    var hi = px(clip.right, clip.top);
    gl.uniform1f(uniform.symOn, 1);
    gl.uniform1f(uniform.symSize, (parseFloat(style.width) || rect.width) / m);
    gl.uniform1f(uniform.symRot, angle);
    gl.uniform1f(uniform.symAlpha, (parseFloat(style.opacity) || 1) * Math.min(1, (seconds() - markBorn) / MARK_FADE));
    gl.uniform2fv(uniform.symC, center);
    gl.uniform2fv(uniform.clipLo, lo);
    gl.uniform2fv(uniform.clipHi, hi);
  }

  // ---- Loop ----
  var lastDraw = 0;
  function draw() {
    var now = seconds();
    age(wakes, wakeBorn, WAKE_LIFE, now);
    age(clicks, clickBorn, CLICK_LIFE, now);
    if (markReady) { placeMark(); }
    gl.uniform1f(uniform.time, now);
    gl.uniform4fv(uniform.wake, wakes);
    gl.uniform4fv(uniform.click, clicks);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    dirty = false;
  }
  var running = false;
  var lastStamp = 0;
  var gaps = [];
  var warm = WARM_UP;
  function giveUp() {
    stopped = true;
    running = false;
    canvas.removeAttribute("data-ready"); // fades out; the static frame was underneath all along
    root.removeAttribute("data-water-mark");
    setTimeout(function () { if (canvas.parentNode) { canvas.parentNode.removeChild(canvas); } }, 2500);
  }
  function judge(stamp) {
    var gap = stamp - lastStamp;
    lastStamp = stamp;
    if (warm > 0) { warm -= 1; return; }
    if (SAVER_PAGE) { return; }
    if (gap > 250) { return; } // the tab was hidden or the page janked for another reason: not the water's fault
    gaps.push(gap);
    if (gaps.length < WINDOW) { return; }
    var average = gaps.reduce(function (sum, value) { return sum + value; }, 0) / gaps.length;
    gaps = [];
    if (average <= (1000 / LEVELS[level].fps) * SLOW) { return; }
    level += 1;
    if (level >= LEVELS.length) { giveUp(); return; }
    warm = WARM_UP;
    resize(); // the next step down: fewer pixels, maybe fewer frames
    draw();
  }
  function frame(stamp) {
    if (stopped || paused || reduced.matches) { running = false; return; }
    requestAnimationFrame(frame); // the browser pauses this while the tab is hidden
    if (stamp - lastDraw < 1000 / LEVELS[level].fps - 2) { return; }
    lastDraw = stamp;
    draw();
    judge(stamp);
  }
  function sync() {
    if (stopped || paused) { return; }
    resize();
    applyColors();
    if (reduced.matches) {
      last = null;
      draw(); // one still frame
    } else if (!running) {
      running = true;
      lastStamp = 0;
      warm = WARM_UP;
      requestAnimationFrame(frame);
    }
  }

  // The router swaps pages without reloading: it tells the water whether the new page wants it.
  var settle = null;
  function toggle(on) {
    if (stopped) { return; }
    clearTimeout(settle);
    if (on) {
      fadeNext = canvas.hasAttribute("data-ready"); // the water is already on screen: only the symbol is new, so it fades in itself
      paused = false;
      mark = document.querySelector(".hero__symbol");
      markReady = false;
      gl.uniform1f(uniform.symOn, 0);
      root.removeAttribute("data-water-mark");
      sync();
      loadMark();
      canvas.setAttribute("data-ready", "");
    } else {
      markReady = false;
      root.removeAttribute("data-water-mark");
      canvas.removeAttribute("data-ready"); // fades out over the static frame, then the loop rests
      settle = setTimeout(function () {
        paused = true;
      }, PAGE_FADE + 50);
    }
  }

  // Mount after the first paint of the page, so the water never delays the text.
  function start() {
    canvas.addEventListener("webglcontextlost", function (event) {
      event.preventDefault();
      canvas.removeAttribute("data-ready");
      root.removeAttribute("data-water-mark");
      running = false;
    });
    document.body.insertBefore(canvas, document.body.firstChild);
    sync();
    loadMark();
    canvas.setAttribute("data-ready", "");
    document.addEventListener("water:toggle", function (event) { toggle(event.detail.on); });
    window.addEventListener("resize", sync);
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerdown", onDown, { passive: true });
    document.addEventListener("pointerleave", function () { last = null; });
    if (reduced.addEventListener) { reduced.addEventListener("change", sync); }
    // Theme button or system change: the tokens change, so the colors are read again.
    new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", sync);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { requestAnimationFrame(start); });
  } else {
    requestAnimationFrame(start);
  }
})();
