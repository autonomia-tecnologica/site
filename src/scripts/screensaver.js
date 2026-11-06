/* Screensaver: one full-window WebGL fragment shader, no libraries.
   The field is a domain-warped noise (the warp feeds the noise back into its own coordinates,
   which makes the slow fluid folds), drawn as soft color bands plus thin glowing contour lines.
   Colors are read from the design tokens (--color-*), so a palette change in tokens.css reaches it.
   It renders at a fraction of the window size and caps the frame rate, so it stays light. */
(function () {
  var RENDER_SCALE = 0.6; // fraction of the window size; the browser smooths the rest
  var MAX_FPS = 30;
  var canvas = document.querySelector("canvas");
  var gl = canvas && canvas.getContext("webgl", { antialias: false, alpha: false, powerPreference: "low-power" });
  if (!gl) { return; }

  var VERTEX = "attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }";
  var FRAGMENT = [
    "precision highp float;",
    "uniform vec2 res; uniform float time;",
    "uniform vec3 cDeep, cGlow, cMain, cLight, cPale;",
    "float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }",
    "float noise(vec2 p) {",
    "  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);",
    "  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);",
    "}",
    "float fbm(vec2 p) {",
    "  float v = 0.0, a = 0.5;",
    "  mat2 r = mat2(0.8, -0.6, 0.6, 0.8);",
    "  for (int i = 0; i < 5; i++) { v += a * noise(p); p = r * p * 2.03 + 11.7; a *= 0.5; }",
    "  return v;",
    "}",
    "void main() {",
    "  vec2 uv = (gl_FragCoord.xy - 0.5 * res) / min(res.x, res.y);",
    "  float t = time * 0.045;",
    "  vec2 p = uv * 2.2;",
    "  vec2 q = vec2(fbm(p + vec2(0.0, t)), fbm(p + vec2(5.2, 1.3) - t));",
    "  vec2 r = vec2(fbm(p + 3.0 * q + vec2(1.7, 9.2) + 1.5 * t), fbm(p + 3.0 * q + vec2(8.3, 2.8) - 1.2 * t));",
    "  float f = fbm(p + 3.2 * r);",
    "  // body: deep purple -> glow -> accent, following the field",
    "  vec3 col = mix(cDeep, cGlow, smoothstep(0.15, 0.55, f));",
    "  col = mix(col, cMain, smoothstep(0.45, 0.85, f) * (0.35 + 0.65 * length(q)));",
    "  col = mix(col, cLight, smoothstep(0.55, 1.0, length(r)) * 0.35);",
    "  // thin contour lines, like the strands of a dream",
    "  float level = f * 9.0 + t * 2.0;",
    "  float line = smoothstep(0.06, 0.0, abs(fract(level) - 0.5) - 0.40);",
    "  col += cPale * line * 0.16 * smoothstep(0.25, 0.8, f);",
    "  // slow breathing halo at the center, echoing the home glow",
    "  float halo = exp(-dot(uv, uv) * 1.6) * (0.5 + 0.5 * sin(time * 0.2));",
    "  col += cGlow * halo * 0.5;",
    "  col *= 1.0 - 0.55 * dot(uv, uv) * 0.6;",
    "  col += (hash(gl_FragCoord.xy + time) - 0.5) / 128.0; // dither: no banding in the gradients",
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

  // Colors come from the tokens. The page is forced to the dark scheme (see the template).
  var styles = getComputedStyle(document.documentElement);
  function token(name) {
    var hex = styles.getPropertyValue(name).trim().replace("#", "");
    if (hex.length === 3) { hex = hex.replace(/./g, "$&$&"); }
    var n = parseInt(hex, 16);
    return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255];
  }
  function color(uniform, name) { gl.uniform3fv(gl.getUniformLocation(program, uniform), token(name)); }
  color("cDeep", "--color-bg");
  color("cGlow", "--color-bg-glow");
  color("cMain", "--color-accent");
  color("cLight", "--color-accent-text");
  color("cPale", "--color-dep-strong");

  var resolution = gl.getUniformLocation(program, "res");
  var clock = gl.getUniformLocation(program, "time");

  function resize() {
    var width = Math.max(2, Math.round(window.innerWidth * RENDER_SCALE));
    var height = Math.max(2, Math.round(window.innerHeight * RENDER_SCALE));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
      gl.uniform2f(resolution, width, height);
    }
  }
  window.addEventListener("resize", resize);
  resize();

  var started = performance.now();
  var last = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    if (now - last < 1000 / MAX_FPS) { return; }
    last = now;
    gl.uniform1f(clock, (now - started) / 1000);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  requestAnimationFrame(frame); // the browser pauses this while the tab is hidden
})();
