"use client";
/* =============================================================================
 *  K-GPT · Landscape.tsx  —  recognizable procedural biomes (R3F components)
 *  -----------------------------------------------------------------------------
 *  Geometry for four readable worlds, cross-faded as the user scrolls:
 *    • Mountains  — snow-capped ridged range + valley lake + distant ridges.
 *    • Beaches    — golden sand into a turquoise sea with a foam shore + palms.
 *    • Waterfalls — mossy cliffs with falling water into a plunge pool + spray.
 *    • Forests    — rolling green hills planted with hundreds of pine trees.
 *
 *  Config + atmosphere stage live in ./biomeConfig; GLSL lives in ./shaders.
 * ========================================================================== */

import * as THREE from "three";
import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  DIVINE_CONFIG,
  BIOME_ORDER,
  VARIANT,
  hillsJS,
  type BiomeKey,
  type Stage,
} from "./biomeConfig";
import {
  TERRAIN_VERT,
  TERRAIN_FRAG,
  WATER_VERT,
  WATER_FRAG,
  FALL_VERT,
  FALL_FRAG,
  MIST_VERT,
  MIST_FRAG,
} from "./shaders";

// Re-export config/atmosphere so consumers can import everything from here.
export {
  DIVINE_CONFIG,
  BIOME_ORDER,
  BIOME_RUNTIME,
  createStage,
  lerpStage,
} from "./biomeConfig";
export type { BiomeKey, Stage, BiomeConfig, BiomeRuntime } from "./biomeConfig";

/* ── Terrain ──────────────────────────────────────────────────────────────── */

function Terrain({ biome }: { biome: BiomeKey }) {
  const cfg = DIVINE_CONFIG.biomes[biome];
  const palette = useMemo(() => {
    const map: Record<BiomeKey, [string, string, string]> = {
      mountains: ["#5d6b62", "#9faaa2", "#5d6b62"],
      beaches: ["#ecdaa6", "#ffffff", "#b59a64"],
      waterfalls: ["#3f5a4c", "#9bb1a2", "#3f5a4c"],
      forests: ["#2f5d34", "#6f9a44", "#2f5d34"],
    };
    return map[biome].map((h) => new THREE.Color(h));
  }, [biome]);

  const uniforms = useMemo(
    () => ({
      uVariant: { value: VARIANT[biome] },
      uAmp: { value: biome === "mountains" ? 13.0 : 1.0 },
      uOpacity: { value: 1 },
      uWaterLevel: { value: cfg.waterLevel },
      uColA: { value: palette[0] },
      uColB: { value: palette[1] },
      uColC: { value: palette[2] },
      uSunDir: { value: new THREE.Vector3(...cfg.sunPosition).normalize() },
      uSunColor: { value: new THREE.Color(cfg.sunColor) },
      uFog: { value: new THREE.Color(cfg.fogColor) },
      uFogDensity: { value: cfg.fogDensity },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [biome],
  );

  const seg = DIVINE_CONFIG.terrainSegments;
  const sz = DIVINE_CONFIG.planeSize;
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} frustumCulled={false}>
      <planeGeometry args={[sz, sz, seg, seg]} />
      <shaderMaterial vertexShader={TERRAIN_VERT} fragmentShader={TERRAIN_FRAG} uniforms={uniforms} transparent />
    </mesh>
  );
}

/* ── Water ────────────────────────────────────────────────────────────────── */

function Water({
  biome,
  size = 300,
  foam = false,
  shoreZ = 10,
  stage,
}: {
  biome: BiomeKey;
  size?: number;
  foam?: boolean;
  shoreZ?: number;
  stage: Stage;
}) {
  const cfg = DIVINE_CONFIG.biomes[biome];
  const mat = useRef<THREE.ShaderMaterial>(null);
  const sunDir = useMemo(() => new THREE.Vector3(), []);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uOpacity: { value: 1 },
      uWaveSpeed: { value: cfg.waveSpeed },
      uWaveHeight: { value: cfg.waveHeight },
      uPointer: { value: new THREE.Vector2(0, -6) },
      uPointerStrength: { value: DIVINE_CONFIG.pointerStrength },
      uShallow: { value: new THREE.Color(cfg.waterShallow) },
      uDeep: { value: new THREE.Color(cfg.waterDeep) },
      uSunDir: { value: new THREE.Vector3() },
      uSunColor: { value: new THREE.Color(cfg.sunColor) },
      uFoam: { value: foam ? 1 : 0 },
      uShoreZ: { value: shoreZ },
      uFog: { value: new THREE.Color(cfg.fogColor) },
      uFogDensity: { value: cfg.fogDensity },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [biome],
  );

  useFrame(() => {
    const m = mat.current;
    if (!m) return;
    const u = m.uniforms;
    u.uTime.value = stage.time;
    u.uPointer.value.copy(stage.pointer);
    u.uSunColor.value.copy(stage.sunColor);
    u.uFog.value.copy(stage.fogColor);
    u.uFogDensity.value = stage.fogDensity;
    u.uSunDir.value.copy(sunDir.copy(stage.sunPosition).normalize());
  });

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, cfg.waterLevel, 0]} frustumCulled={false}>
      <planeGeometry args={[size, size, 120, 120]} />
      <shaderMaterial ref={mat} vertexShader={WATER_VERT} fragmentShader={WATER_FRAG} uniforms={uniforms} transparent depthWrite={false} />
    </mesh>
  );
}

/* ── Falling water (waterfall) ────────────────────────────────────────────── */

function FallingWater({ stage }: { stage: Stage }) {
  const mats = useRef<THREE.ShaderMaterial[]>([]);
  const falls = useMemo(
    () =>
      [
        { x: -10, w: 7, h: 17, y: 5.5, z: -23.5 },
        { x: 2, w: 9, h: 18, y: 6, z: -24 },
        { x: 13, w: 6, h: 16, y: 5, z: -23.5 },
      ].map((f) => ({
        ...f,
        u: { uTime: { value: 0 }, uOpacity: { value: 1 }, uColor: { value: new THREE.Color("#bfeede") } },
      })),
    [],
  );

  useFrame(() => {
    mats.current.forEach((m) => m && (m.uniforms.uTime.value = stage.time));
  });

  return (
    <group>
      {falls.map((f, i) => (
        <mesh key={i} position={[f.x, f.y, f.z]}>
          <planeGeometry args={[f.w, f.h, 1, 1]} />
          <shaderMaterial
            ref={(r) => {
              if (r) mats.current[i] = r;
            }}
            vertexShader={FALL_VERT}
            fragmentShader={FALL_FRAG}
            uniforms={f.u}
            transparent
            depthWrite={false}
            side={THREE.DoubleSide}
          />
        </mesh>
      ))}
    </group>
  );
}

/* ── Trees (instanced pines) ──────────────────────────────────────────────── */

function Trees() {
  const trunkRef = useRef<THREE.InstancedMesh>(null);
  const canopyRef = useRef<THREE.InstancedMesh>(null);
  const n = DIVINE_CONFIG.treeCount;
  const built = useRef(false);

  const data = useMemo(() => {
    const arr: { x: number; z: number; s: number; r: number; tint: THREE.Color }[] = [];
    for (let i = 0; i < n; i++) {
      const x = (Math.random() - 0.5) * 150;
      const z = -8 - Math.random() * 130;
      arr.push({
        x,
        z,
        s: 1.4 + Math.random() * 2.6,
        r: Math.random() * Math.PI * 2,
        tint: new THREE.Color().setHSL(0.28 + Math.random() * 0.07, 0.45, 0.28 + Math.random() * 0.12),
      });
    }
    return arr;
  }, [n]);

  useFrame(() => {
    if (built.current || !trunkRef.current || !canopyRef.current) return;
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    data.forEach((d, i) => {
      const groundY = hillsJS(d.x, -d.z);
      q.setFromAxisAngle(up, d.r);
      m.compose(new THREE.Vector3(d.x, groundY + 0.6 * d.s, d.z), q, new THREE.Vector3(d.s, d.s, d.s));
      trunkRef.current!.setMatrixAt(i, m);
      m.compose(new THREE.Vector3(d.x, groundY + 2.4 * d.s, d.z), q, new THREE.Vector3(d.s, d.s * 1.2, d.s));
      canopyRef.current!.setMatrixAt(i, m);
      canopyRef.current!.setColorAt(i, d.tint);
    });
    trunkRef.current.instanceMatrix.needsUpdate = true;
    canopyRef.current.instanceMatrix.needsUpdate = true;
    if (canopyRef.current.instanceColor) canopyRef.current.instanceColor.needsUpdate = true;
    built.current = true;
  });

  return (
    <group>
      <instancedMesh ref={trunkRef} args={[undefined, undefined, n]} frustumCulled={false}>
        <cylinderGeometry args={[0.13, 0.2, 1.2, 5]} />
        <meshStandardMaterial color="#5a4632" roughness={1} transparent />
      </instancedMesh>
      <instancedMesh ref={canopyRef} args={[undefined, undefined, n]} frustumCulled={false}>
        <coneGeometry args={[1.0, 2.8, 7]} />
        <meshStandardMaterial color="#ffffff" roughness={1} transparent />
      </instancedMesh>
    </group>
  );
}

/* ── Palms (beach) ────────────────────────────────────────────────────────── */

function Palm({ position, scale = 1 }: { position: [number, number, number]; scale?: number }) {
  const fronds = useMemo(() => [0, 1, 2, 3, 4, 5], []);
  return (
    <group position={position} scale={scale}>
      <mesh position={[0, 2.4, 0]} rotation={[0, 0, 0.12]}>
        <cylinderGeometry args={[0.16, 0.28, 5, 6]} />
        <meshStandardMaterial color="#7a5a36" roughness={1} transparent />
      </mesh>
      {fronds.map((f) => (
        <mesh
          key={f}
          position={[Math.cos((f / 6) * Math.PI * 2) * 0.6 + 0.6, 5, Math.sin((f / 6) * Math.PI * 2) * 0.6]}
          rotation={[0.5, (f / 6) * Math.PI * 2, 0]}
        >
          <coneGeometry args={[0.5, 3.4, 4]} />
          <meshStandardMaterial color="#3f8a4a" roughness={1} transparent />
        </mesh>
      ))}
    </group>
  );
}

function Palms() {
  const spots: [number, number, number][] = [
    [-16, 1.2, 2],
    [12, 1.0, -4],
    [22, 1.4, 6],
    [-26, 1.2, -6],
  ];
  return (
    <group>
      {spots.map((p, i) => (
        <Palm key={i} position={p} scale={1 + (i % 2) * 0.3} />
      ))}
    </group>
  );
}

/* ── Distant ridge silhouettes (mountains) ────────────────────────────────── */

function Ridges() {
  const layers = [
    { z: -120, y: 4, color: "#7e97b8", scaleY: 22 },
    { z: -150, y: 6, color: "#9fb3cf", scaleY: 28 },
    { z: -180, y: 8, color: "#bccbe0", scaleY: 34 },
  ];
  return (
    <group>
      {layers.map((l, i) => (
        <mesh key={i} position={[0, l.y, l.z]}>
          <planeGeometry args={[420, l.scaleY, 60, 1]} />
          <meshBasicMaterial color={l.color} transparent opacity={0.9} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}

/* ── Mist particles (shared) ──────────────────────────────────────────────── */

function Mist({ stage }: { stage: Stage }) {
  const mat = useRef<THREE.ShaderMaterial>(null);
  const { positions, seeds, scales } = useMemo(() => {
    const nn = DIVINE_CONFIG.particleCount;
    const positions = new Float32Array(nn * 3);
    const seeds = new Float32Array(nn);
    const scales = new Float32Array(nn);
    for (let i = 0; i < nn; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 160;
      positions[i * 3 + 1] = Math.random() * 56;
      positions[i * 3 + 2] = -10 - Math.random() * 120;
      seeds[i] = Math.random();
      scales[i] = 0.4 + Math.random() * 1.0;
    }
    return { positions, seeds, scales };
  }, []);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSize: { value: stage.particleSize },
      uWind: { value: stage.windIntensity },
      uRise: { value: stage.riseSpeed },
      uDensity: { value: stage.particleDensity },
      uColor: { value: stage.particleColor.clone() },
      uOpacity: { value: 1 },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useFrame(() => {
    const m = mat.current;
    if (!m) return;
    const u = m.uniforms;
    u.uTime.value = stage.time;
    u.uSize.value = stage.particleSize;
    u.uWind.value = stage.windIntensity;
    u.uRise.value = stage.riseSpeed;
    u.uDensity.value = stage.particleDensity;
    u.uColor.value.copy(stage.particleColor);
  });

  return (
    <points frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-aSeed" args={[seeds, 1]} />
        <bufferAttribute attach="attributes-aScale" args={[scales, 1]} />
      </bufferGeometry>
      <shaderMaterial ref={mat} vertexShader={MIST_VERT} fragmentShader={MIST_FRAG} uniforms={uniforms} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </points>
  );
}

/* ── Per-biome groups + cross-fade ────────────────────────────────────────── */

function BiomeGroup({ biome, stage }: { biome: BiomeKey; stage: Stage }) {
  switch (biome) {
    case "mountains":
      return (
        <group>
          <Ridges />
          <Terrain biome="mountains" />
          <Water biome="mountains" size={120} stage={stage} />
        </group>
      );
    case "beaches":
      return (
        <group>
          <Terrain biome="beaches" />
          <Water biome="beaches" size={300} foam shoreZ={10} stage={stage} />
          <Palms />
        </group>
      );
    case "waterfalls":
      return (
        <group>
          <Terrain biome="waterfalls" />
          <Water biome="waterfalls" size={120} stage={stage} />
          <FallingWater stage={stage} />
        </group>
      );
    case "forests":
      return (
        <group>
          <Terrain biome="forests" />
          <Water biome="forests" size={70} stage={stage} />
          <Trees />
        </group>
      );
  }
}

function FadeGroup({ biome, active, stage }: { biome: BiomeKey; active: BiomeKey; stage: Stage }) {
  const ref = useRef<THREE.Group>(null);
  const weight = useRef(biome === active ? 1 : 0);

  useFrame(() => {
    const target = biome === active ? 1 : 0;
    weight.current += (target - weight.current) * DIVINE_CONFIG.crossFadeEase;
    const g = ref.current;
    if (!g) return;
    const w = weight.current;
    g.visible = w > 0.012;
    if (!g.visible) return;
    g.traverse((o) => {
      const mesh = o as THREE.Mesh;
      const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
      if (!mat) return;
      const apply = (mm: THREE.Material) => {
        const sm = mm as THREE.ShaderMaterial;
        if (sm.uniforms && sm.uniforms.uOpacity) sm.uniforms.uOpacity.value = w;
        else {
          mm.transparent = true;
          mm.opacity = w;
        }
      };
      Array.isArray(mat) ? mat.forEach(apply) : apply(mat);
    });
  });

  return (
    <group ref={ref} visible={biome === active}>
      <BiomeGroup biome={biome} stage={stage} />
    </group>
  );
}

export function Landscape({ stage, biome }: { stage: Stage; biome: BiomeKey }) {
  useFrame((state) => {
    const tx = state.pointer.x * 50;
    const tz = -state.pointer.y * 26 - 6;
    stage.pointer.x += (tx - stage.pointer.x) * DIVINE_CONFIG.pointerEase;
    stage.pointer.y += (tz - stage.pointer.y) * DIVINE_CONFIG.pointerEase;
  });

  return (
    <group>
      {BIOME_ORDER.map((k) => (
        <FadeGroup key={k} biome={k} active={biome} stage={stage} />
      ))}
      <Mist stage={stage} />
    </group>
  );
}

export default Landscape;
