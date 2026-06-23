/* =============================================================================
 *  K-GPT · biomeConfig.ts  —  data + atmosphere stage (no JSX)
 *  Adjustable knobs per biome: sun, camera framing, water, particles, wind.
 * ========================================================================== */

import * as THREE from "three";

export type BiomeKey = "mountains" | "beaches" | "waterfalls" | "forests";

export interface BiomeConfig {
  label: string;
  caption: string;
  sunPosition: [number, number, number];
  sunColor: string;
  skyTop: string;
  skyHorizon: string;
  fogColor: string;
  fogDensity: number;
  cameraPos: [number, number, number];
  cameraTarget: [number, number, number];
  waterShallow: string;
  waterDeep: string;
  waterLevel: number;
  waveSpeed: number;
  waveHeight: number;
  particleColor: string;
  particleDensity: number;
  particleSize: number;
  riseSpeed: number;
  windIntensity: number;
}

export const DIVINE_CONFIG = {
  particleCount: 3600,
  terrainSegments: 200,
  planeSize: 300,
  pointerEase: 0.06,
  pointerStrength: 0.4,
  biomeMorphEase: 0.04,
  crossFadeEase: 0.05,
  treeCount: 190,

  biomes: {
    mountains: {
      label: "Mountains",
      caption: "Clarity at altitude — a calm, focused place to think.",
      sunPosition: [-60, 38, -90],
      sunColor: "#fff0d0",
      skyTop: "#1f4f8f",
      skyHorizon: "#cfe4ff",
      fogColor: "#bcd2ea",
      fogDensity: 0.0062,
      cameraPos: [0, 7, 30],
      cameraTarget: [0, 12, -50],
      waterShallow: "#5f96b8",
      waterDeep: "#1a3550",
      waterLevel: 0.0,
      waveSpeed: 0.4,
      waveHeight: 0.12,
      particleColor: "#ffffff",
      particleDensity: 0.32,
      particleSize: 3.2,
      riseSpeed: -0.25,
      windIntensity: 0.45,
    },
    beaches: {
      label: "Beaches",
      caption: "Open horizons — room to learn, create, and breathe.",
      sunPosition: [55, 16, -80],
      sunColor: "#ffd79a",
      skyTop: "#2a82c8",
      skyHorizon: "#ffe7bf",
      fogColor: "#ffe6c8",
      fogDensity: 0.0055,
      cameraPos: [0, 4.5, 30],
      cameraTarget: [0, 2.5, -60],
      waterShallow: "#28c4d8",
      waterDeep: "#077a92",
      waterLevel: 0.0,
      waveSpeed: 0.8,
      waveHeight: 0.16,
      particleColor: "#fff4dc",
      particleDensity: 0.22,
      particleSize: 2.6,
      riseSpeed: 0.12,
      windIntensity: 0.7,
    },
    waterfalls: {
      label: "Waterfalls",
      caption: "Momentum and flow — energy for deep, immersive work.",
      sunPosition: [30, 40, -70],
      sunColor: "#eafff7",
      skyTop: "#1c5256",
      skyHorizon: "#c4ece0",
      fogColor: "#cfeae3",
      fogDensity: 0.0075,
      cameraPos: [0, 8, 30],
      cameraTarget: [0, 9, -45],
      waterShallow: "#22c2a6",
      waterDeep: "#0a4a45",
      waterLevel: -1.6,
      waveSpeed: 1.2,
      waveHeight: 0.12,
      particleColor: "#f4fffb",
      particleDensity: 0.85,
      particleSize: 4.5,
      riseSpeed: 0.9,
      windIntensity: 0.4,
    },
    forests: {
      label: "Forests",
      caption: "Grounded and green — steady focus for the long haul.",
      sunPosition: [-40, 30, -70],
      sunColor: "#ffe7a0",
      skyTop: "#2b5a32",
      skyHorizon: "#dceca6",
      fogColor: "#c9deb0",
      fogDensity: 0.0072,
      cameraPos: [0, 9, 30],
      cameraTarget: [0, 4, -45],
      waterShallow: "#3a8f6a",
      waterDeep: "#123f2d",
      waterLevel: -0.4,
      waveSpeed: 0.4,
      waveHeight: 0.06,
      particleColor: "#ffe98a",
      particleDensity: 0.6,
      particleSize: 3.4,
      riseSpeed: 0.3,
      windIntensity: 0.85,
    },
  } as Record<BiomeKey, BiomeConfig>,
};

export const BIOME_ORDER: BiomeKey[] = ["mountains", "beaches", "waterfalls", "forests"];
export const VARIANT: Record<BiomeKey, number> = { mountains: 0, beaches: 1, waterfalls: 2, forests: 3 };

/* JS twin of the GLSL hills() — used to plant trees on the forest floor. */
export function hillsJS(x: number, y: number) {
  return Math.sin(x * 0.15) * 1.2 + Math.cos(y * 0.13) * 1.0 + Math.sin((x + y) * 0.07) * 1.5;
}

/* ── Atmosphere stage (lerped toward the active biome each frame) ─────────── */

export interface BiomeRuntime {
  sunPosition: THREE.Vector3;
  sunColor: THREE.Color;
  skyTop: THREE.Color;
  skyHorizon: THREE.Color;
  fogColor: THREE.Color;
  fogDensity: number;
  cameraPos: THREE.Vector3;
  cameraTarget: THREE.Vector3;
  particleColor: THREE.Color;
  particleDensity: number;
  particleSize: number;
  riseSpeed: number;
  windIntensity: number;
}

function toRuntime(c: BiomeConfig): BiomeRuntime {
  return {
    sunPosition: new THREE.Vector3(...c.sunPosition),
    sunColor: new THREE.Color(c.sunColor),
    skyTop: new THREE.Color(c.skyTop),
    skyHorizon: new THREE.Color(c.skyHorizon),
    fogColor: new THREE.Color(c.fogColor),
    fogDensity: c.fogDensity,
    cameraPos: new THREE.Vector3(...c.cameraPos),
    cameraTarget: new THREE.Vector3(...c.cameraTarget),
    particleColor: new THREE.Color(c.particleColor),
    particleDensity: c.particleDensity,
    particleSize: c.particleSize,
    riseSpeed: c.riseSpeed,
    windIntensity: c.windIntensity,
  };
}

export const BIOME_RUNTIME: Record<BiomeKey, BiomeRuntime> = {
  mountains: toRuntime(DIVINE_CONFIG.biomes.mountains),
  beaches: toRuntime(DIVINE_CONFIG.biomes.beaches),
  waterfalls: toRuntime(DIVINE_CONFIG.biomes.waterfalls),
  forests: toRuntime(DIVINE_CONFIG.biomes.forests),
};

export interface Stage extends BiomeRuntime {
  time: number;
  pointer: THREE.Vector2;
}

export function createStage(key: BiomeKey): Stage {
  const r = BIOME_RUNTIME[key];
  return {
    sunPosition: r.sunPosition.clone(),
    sunColor: r.sunColor.clone(),
    skyTop: r.skyTop.clone(),
    skyHorizon: r.skyHorizon.clone(),
    fogColor: r.fogColor.clone(),
    fogDensity: r.fogDensity,
    cameraPos: r.cameraPos.clone(),
    cameraTarget: r.cameraTarget.clone(),
    particleColor: r.particleColor.clone(),
    particleDensity: r.particleDensity,
    particleSize: r.particleSize,
    riseSpeed: r.riseSpeed,
    windIntensity: r.windIntensity,
    time: 0,
    pointer: new THREE.Vector2(0, -6),
  };
}

const lf = THREE.MathUtils.lerp;

export function lerpStage(stage: Stage, target: BiomeRuntime, t: number) {
  stage.sunPosition.lerp(target.sunPosition, t);
  stage.sunColor.lerp(target.sunColor, t);
  stage.skyTop.lerp(target.skyTop, t);
  stage.skyHorizon.lerp(target.skyHorizon, t);
  stage.fogColor.lerp(target.fogColor, t);
  stage.fogDensity = lf(stage.fogDensity, target.fogDensity, t);
  stage.cameraPos.lerp(target.cameraPos, t);
  stage.cameraTarget.lerp(target.cameraTarget, t);
  stage.particleColor.lerp(target.particleColor, t);
  stage.particleDensity = lf(stage.particleDensity, target.particleDensity, t);
  stage.particleSize = lf(stage.particleSize, target.particleSize, t);
  stage.riseSpeed = lf(stage.riseSpeed, target.riseSpeed, t);
  stage.windIntensity = lf(stage.windIntensity, target.windIntensity, t);
}
