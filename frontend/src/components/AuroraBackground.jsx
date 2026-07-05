import { useEffect, useRef } from 'react';

// Full-viewport WebGL market nebula: domain-warped fbm aurora in the brand
// emerald/cyan, drifting data sparks, mouse parallax. Renders behind the app
// (z-index 0, pointer-events none). Falls back to the static CSS gradient on
// body when WebGL is unavailable, and renders a single still frame when the
// user prefers reduced motion.

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform vec2 uMouse;

float hash(vec2 p) {
  p = fract(p * vec2(234.34, 435.345));
  p += dot(p, p + 34.23);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float amp = 0.55;
  mat2 rot = mat2(0.8, 0.6, -0.6, 0.8);
  for (int i = 0; i < 5; i++) {
    v += amp * noise(p);
    p = rot * p * 2.02;
    amp *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  float t = uTime * 0.045;
  vec2 par = uMouse * 0.05;

  // Domain-warped nebula
  vec2 p = uv * 1.55 + par;
  float q = fbm(p + vec2(t * 0.9, -t * 0.35));
  float r = fbm(p + 3.6 * q + vec2(1.7, 9.2) + vec2(t * 0.18, t * 0.22));
  float v = fbm(p + 2.8 * r);

  vec3 deep    = vec3(0.012, 0.024, 0.050);
  vec3 navy    = vec3(0.040, 0.075, 0.140);
  vec3 emerald = vec3(0.204, 0.827, 0.598);
  vec3 cyan    = vec3(0.247, 0.776, 0.941);

  vec3 col = deep;
  col = mix(col, navy, smoothstep(0.12, 0.92, v));
  col += emerald * pow(smoothstep(0.48, 0.98, v), 3.0) * 0.50;
  col += cyan * pow(smoothstep(0.55, 1.05, r), 4.0) * 0.32;

  // Horizon glow behind the hero
  float d = length(uv - vec2(0.0, 0.42));
  col += emerald * 0.09 * exp(-d * 3.2);
  col += cyan * 0.05 * exp(-length(uv - vec2(0.45, 0.30)) * 4.0);

  // Rising data sparks
  vec2 gp = vec2(uv.x * 22.0, uv.y * 22.0 - uTime * 0.55);
  vec2 cell = floor(gp);
  float star = hash(cell);
  if (star > 0.985) {
    vec2 local = fract(gp) - 0.5;
    float twinkle = 0.5 + 0.5 * sin(uTime * (1.5 + star * 3.0) + star * 40.0);
    float glow = exp(-dot(local, local) * 26.0) * twinkle;
    col += mix(emerald, cyan, hash(cell + 7.7)) * glow * 0.55;
  }

  // Vignette + subtle grain
  float vig = smoothstep(1.35, 0.30, length(uv));
  col *= mix(0.5, 1.0, vig);
  col += (hash(gl_FragCoord.xy + fract(uTime)) - 0.5) * 0.016;

  gl_FragColor = vec4(col, 1.0);
}
`;

export default function AuroraBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    canvas.style.display = '';

    // On failure at any stage, hide the canvas so the body CSS gradient shows
    // (a broken WebGL surface can composite as opaque white).
    const bail = () => { canvas.style.display = 'none'; return undefined; };

    let gl;
    try {
      gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' });
    } catch {
      gl = null;
    }
    if (!gl || gl.isContextLost()) return bail();
    gl.clearColor(0.02, 0.031, 0.059, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    const compile = (type, src) => {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        console.warn('Aurora shader failed:', gl.getShaderInfoLog(sh));
        return null;
      }
      return sh;
    };

    const vs = compile(gl.VERTEX_SHADER, VERT);
    const fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return bail();

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return bail();
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'aPos');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(prog, 'uRes');
    const uTime = gl.getUniformLocation(prog, 'uTime');
    const uMouse = gl.getUniformLocation(prog, 'uMouse');

    // Render at reduced resolution — the nebula is soft, full DPR is wasted GPU
    const scale = Math.min(window.devicePixelRatio || 1, 1.5) * 0.62;
    const resize = () => {
      canvas.width = Math.max(1, Math.floor(window.innerWidth * scale));
      canvas.height = Math.max(1, Math.floor(window.innerHeight * scale));
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    resize();

    const mouse = { x: 0, y: 0, tx: 0, ty: 0 };
    const onMove = (e) => {
      mouse.tx = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.ty = -((e.clientY / window.innerHeight) * 2 - 1);
    };

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0;
    let running = true;
    const start = performance.now();

    const frame = () => {
      mouse.x += (mouse.tx - mouse.x) * 0.04;
      mouse.y += (mouse.ty - mouse.y) * 0.04;
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, (performance.now() - start) / 1000);
      gl.uniform2f(uMouse, mouse.x, mouse.y);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (running && !reduced) raf = requestAnimationFrame(frame);
    };

    const onVisibility = () => {
      running = document.visibilityState === 'visible';
      if (running && !reduced) {
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(frame);
      }
    };

    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', onMove, { passive: true });
    document.addEventListener('visibilitychange', onVisibility);
    raf = requestAnimationFrame(frame);

    return () => {
      // No loseContext() here: StrictMode remounts reuse the same canvas, and
      // getContext() would hand back the same, now-dead context.
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMove);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return <canvas ref={canvasRef} className="aurora-canvas" aria-hidden="true" />;
}
