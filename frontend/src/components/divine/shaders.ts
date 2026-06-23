/* =============================================================================
 *  K-GPT · shaders.ts  —  GLSL for the divine biomes
 *  Simplex noise + fbm/ridged/hills, terrain (variant-driven), water, falling
 *  water and mist particles. Kept separate so no single source file is huge.
 * ========================================================================== */

export const GLSL_NOISE = /* glsl */ `
vec3 mod289(vec3 x){ return x - floor(x*(1.0/289.0))*289.0; }
vec4 mod289(vec4 x){ return x - floor(x*(1.0/289.0))*289.0; }
vec4 permute(vec4 x){ return mod289(((x*34.0)+1.0)*x); }
vec4 taylorInvSqrt(vec4 r){ return 1.79284291400159 - 0.85373472095314 * r; }
float snoise(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
            i.z + vec4(0.0, i1.z, i2.z, 1.0))
          + i.y + vec4(0.0, i1.y, i2.y, 1.0))
          + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0)*2.0 + 1.0;
  vec4 s1 = floor(b1)*2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}
float fbm(vec2 p){ float h=0.0, a=0.5; for(int i=0;i<5;i++){ h += a*snoise(vec3(p,0.0)); p*=2.02; a*=0.5; } return h; }
float ridged(vec2 p){ float h=0.0,a=0.5,f=1.0; for(int i=0;i<5;i++){ float n=snoise(vec3(p*f,11.0)); h+=a*(1.0-abs(n)); f*=2.03; a*=0.5; } return h; }
float hills(vec2 p){ return sin(p.x*0.15)*1.2 + cos(p.y*0.13)*1.0 + sin((p.x+p.y)*0.07)*1.5; }
`;

/* ── Terrain (one variant-driven shader for all four ground types) ────────── */

export const TERRAIN_VERT = /* glsl */ `
${GLSL_NOISE}
uniform float uVariant;
uniform float uAmp;
varying float vH;
varying vec3  vNormal;
varying vec3  vWorld;

float heightFor(vec2 p){
  if (uVariant < 0.5){            // MOUNTAINS — valley near, peaks far
    float t = smoothstep(-30.0, 90.0, p.y);
    float r = ridged(p * 0.03);
    return mix(-3.0, 1.0, t) + r * uAmp * smoothstep(-6.0, 70.0, p.y);
  } else if (uVariant < 1.5){     // BEACH — sand near, sea far
    float t = smoothstep(-30.0, 45.0, p.y);
    float dunes = fbm(p * 0.05) * 0.7;
    return mix(2.2, -6.0, t) + dunes * (1.0 - t);
  } else if (uVariant < 2.5){     // WATERFALL — pool near, cliff + plateau far
    float wall = smoothstep(16.0, 30.0, p.y);
    float h = mix(-3.0, 13.0, wall);
    h += smoothstep(34.0, 80.0, p.y) * 6.0;
    h += fbm(p * 0.06) * 1.6 * wall;
    return h;
  }                               // FOREST — rolling hills (matches hillsJS)
  return hills(p) + fbm(p * 0.1) * 0.6;
}

void main(){
  vec3 pos = position;
  float h = heightFor(pos.xy);
  pos.z += h;
  float e = 1.0;
  float dhx = (heightFor(pos.xy + vec2(e,0.0)) - heightFor(pos.xy - vec2(e,0.0))) / (2.0*e);
  float dhy = (heightFor(pos.xy + vec2(0.0,e)) - heightFor(pos.xy - vec2(0.0,e))) / (2.0*e);
  vNormal = normalize(normalMatrix * normalize(vec3(-dhx, -dhy, 1.0)));
  vH = h;
  vec4 wp = modelMatrix * vec4(pos, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}
`;

export const TERRAIN_FRAG = /* glsl */ `
uniform float uVariant;
uniform float uAmp;
uniform float uOpacity;
uniform float uWaterLevel;
uniform vec3  uColA;
uniform vec3  uColB;
uniform vec3  uColC;
uniform vec3  uSunDir;
uniform vec3  uSunColor;
uniform vec3  uFog;
uniform float uFogDensity;
varying float vH;
varying vec3  vNormal;
varying vec3  vWorld;

void main(){
  vec3 N = normalize(vNormal);
  float diff = clamp(dot(N, normalize(uSunDir)), 0.0, 1.0);
  float light = 0.42 + 0.75 * diff;
  vec3 col;

  if (uVariant < 0.5){
    float elev = clamp(vH / uAmp, 0.0, 1.0);
    col = mix(uColA, uColB, smoothstep(0.1, 0.7, elev));
    float snow = smoothstep(0.5, 0.72, elev) * smoothstep(0.55, 0.85, N.y);
    col = mix(col, vec3(0.97, 0.99, 1.0), snow);
  } else if (uVariant < 1.5){
    float wet = smoothstep(0.5, -0.2, vH - uWaterLevel);
    float foam = smoothstep(0.35, 0.0, abs(vH - uWaterLevel));
    col = mix(uColA, uColC, wet);
    col = mix(col, vec3(1.0), foam * 0.7);
  } else if (uVariant < 2.5){
    float elev = clamp(vH / 14.0, 0.0, 1.0);
    col = mix(uColA, uColB, smoothstep(0.0, 0.8, elev));
  } else {
    float elev = clamp((vH + 4.0) / 9.0, 0.0, 1.0);
    col = mix(uColA, uColB, smoothstep(0.2, 0.9, elev) * smoothstep(0.4, 0.95, N.y));
  }

  col *= light * uSunColor;
  float dist = length(vWorld - cameraPosition);
  col = mix(col, uFog, clamp(1.0 - exp(-uFogDensity * dist), 0.0, 1.0));
  gl_FragColor = vec4(col, uOpacity);
}
`;

/* ── Water (sea / pool / lake) with optional foam shoreline ───────────────── */

export const WATER_VERT = /* glsl */ `
${GLSL_NOISE}
uniform float uTime;
uniform float uWaveSpeed;
uniform float uWaveHeight;
uniform vec2  uPointer;
uniform float uPointerStrength;
varying vec3  vWorld;
varying vec3  vNormal;

float waveH(vec2 p, float t){
  return sin(p.x*0.2 + t*1.1)*0.5 + sin(p.y*0.15 - t*0.9)*0.4 + snoise(vec3(p*0.08, t*0.25))*0.6;
}
void main(){
  vec3 pos = position;
  float t = uTime * uWaveSpeed;
  float h = waveH(pos.xy, t) * uWaveHeight;
  float d = distance(pos.xy, uPointer);
  h += sin(d*0.6 - uTime*3.0) * exp(-d*0.08) * uPointerStrength;
  pos.z += h;
  float e = 0.7;
  float dhx = (waveH(pos.xy+vec2(e,0.0),t) - waveH(pos.xy-vec2(e,0.0),t)) * uWaveHeight / (2.0*e);
  float dhy = (waveH(pos.xy+vec2(0.0,e),t) - waveH(pos.xy-vec2(0.0,e),t)) * uWaveHeight / (2.0*e);
  vNormal = normalize(normalMatrix * normalize(vec3(-dhx, -dhy, 1.0)));
  vec4 wp = modelMatrix * vec4(pos, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}
`;

export const WATER_FRAG = /* glsl */ `
${GLSL_NOISE}
uniform float uTime;
uniform float uOpacity;
uniform vec3  uShallow;
uniform vec3  uDeep;
uniform vec3  uSunDir;
uniform vec3  uSunColor;
uniform float uFoam;
uniform float uShoreZ;
uniform vec3  uFog;
uniform float uFogDensity;
varying vec3  vWorld;
varying vec3  vNormal;

void main(){
  vec3 N = normalize(vNormal);
  vec3 V = normalize(cameraPosition - vWorld);
  float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 3.0);
  vec3 col = mix(uDeep, uShallow, clamp(fres + 0.3, 0.0, 1.0));

  vec3 H = normalize(normalize(uSunDir) + V);
  col += pow(clamp(dot(N, H), 0.0, 1.0), 120.0) * uSunColor * 1.0;

  if (uFoam > 0.5){
    float band = smoothstep(5.0, 0.0, abs(vWorld.z - uShoreZ));
    float n = snoise(vec3(vWorld.xz * 0.3, uTime * 0.6));
    col = mix(col, vec3(1.0), band * smoothstep(0.0, 0.6, n) * 0.8);
  }

  float dist = length(vWorld - cameraPosition);
  col = mix(col, uFog, clamp(1.0 - exp(-uFogDensity * dist), 0.0, 1.0));
  gl_FragColor = vec4(col, mix(0.8, 0.97, fres) * uOpacity);
}
`;

/* ── Falling water (waterfall cascade quads) ──────────────────────────────── */

export const FALL_VERT = /* glsl */ `
varying vec2 vUv;
void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;

export const FALL_FRAG = /* glsl */ `
${GLSL_NOISE}
uniform float uTime;
uniform float uOpacity;
uniform vec3  uColor;
varying vec2  vUv;
void main(){
  float streak = snoise(vec3(vUv.x * 26.0, vUv.y * 3.0 - uTime * 3.2, 0.0));
  float flow = 0.55 + 0.45 * snoise(vec3(vUv.x * 10.0, vUv.y * 6.0 - uTime * 5.0, 4.0));
  float bright = clamp(flow + streak * 0.3, 0.0, 1.0);
  vec3 col = mix(uColor * 0.7, vec3(1.0), bright);
  float edge = smoothstep(0.0, 0.12, vUv.x) * smoothstep(1.0, 0.88, vUv.x);
  float top = smoothstep(0.0, 0.08, vUv.y);
  gl_FragColor = vec4(col, (0.5 + 0.5 * bright) * edge * top * uOpacity);
}
`;

/* ── Mist particles ───────────────────────────────────────────────────────── */

export const MIST_VERT = /* glsl */ `
uniform float uTime;
uniform float uSize;
uniform float uWind;
uniform float uRise;
uniform float uDensity;
attribute float aSeed;
attribute float aScale;
varying float vAlpha;
void main(){
  vec3 p = position;
  float t = uTime;
  float col = mod(p.y + t * uRise * 2.0 + aSeed * 40.0, 56.0);
  p.y = col - 6.0;
  p.x += sin(t * 0.6 + aSeed * 6.2831) * uWind * (1.0 + aScale);
  p.z += cos(t * 0.45 + aSeed * 6.2831) * uWind * 0.6;
  vAlpha = smoothstep(0.0, 6.0, p.y + 6.0) * (1.0 - smoothstep(36.0, 50.0, col));
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  float vis = step(aSeed, uDensity) * step(0.5, -mv.z);
  vAlpha *= vis;
  float ps = uSize * aScale * (150.0 / max(-mv.z, 1.0));
  gl_PointSize = clamp(ps, 0.0, 48.0) * vis;
  gl_Position = projectionMatrix * mv;
}
`;

export const MIST_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
varying float vAlpha;
void main(){
  vec2 c = gl_PointCoord - 0.5;
  float d = length(c);
  if (d > 0.5) discard;
  gl_FragColor = vec4(uColor, (1.0 - smoothstep(0.05, 0.5, d)) * vAlpha * 0.6 * uOpacity);
}
`;
