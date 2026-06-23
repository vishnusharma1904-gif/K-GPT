"use client";
/* =============================================================================
 *  K-GPT · DivineCanvas.tsx
 *  -----------------------------------------------------------------------------
 *  The full-screen React Three Fiber <Canvas> that hosts the divine world:
 *
 *    • A glowing gradient skybox with a real sun disk + halo.
 *    • The procedural Landscape (terrain / ocean / mist) from ./Landscape.
 *    • Post-processing: volumetric God Rays streaming from the sun, a soft Bloom
 *      that ignites the water's specular highlights, and a gentle Vignette.
 *    • A StageMorph controller that lerps the shared `Stage` toward the active
 *      biome each frame, so scrolling between sections feels like a slow breath.
 *
 *  Suspense wraps the scene for graceful shader/asset loading, backed by an
 *  elegant DOM veil that fades away once the first frame has been painted.
 *
 *  NOTE: import this with `next/dynamic({ ssr:false })` — WebGL is client-only.
 * ========================================================================== */

import * as THREE from "three";
import { Suspense, useMemo, useRef, useState, Component, type ReactNode } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { EffectComposer, Bloom, GodRays, Vignette } from "@react-three/postprocessing";
import { BlendFunction, KernelSize } from "postprocessing";
import {
  DIVINE_CONFIG,
  BIOME_RUNTIME,
  createStage,
  lerpStage,
  Landscape,
  type BiomeKey,
  type Stage,
} from "./Landscape";

/* =============================================================================
 *  Glowing skybox  —  vertical gradient + sun disk & halo
 * ========================================================================== */

const SKY_VERT = /* glsl */ `
varying vec3 vDir;
void main(){
  vDir = position;                       // direction from the sphere's centre
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const SKY_FRAG = /* glsl */ `
uniform vec3 uTop;
uniform vec3 uHorizon;
uniform vec3 uSunColor;
uniform vec3 uSunDir;       // normalised direction TO the sun
varying vec3 vDir;
void main(){
  vec3 dir = normalize(vDir);
  float t = clamp(dir.y * 0.5 + 0.5, 0.0, 1.0);
  vec3 col = mix(uHorizon, uTop, pow(t, 0.8));

  // Sun: a tight disk plus a broad atmospheric halo.
  float s = max(dot(dir, normalize(uSunDir)), 0.0);
  col += uSunColor * pow(s, 520.0) * 2.6;   // tight disk
  col += uSunColor * pow(s, 14.0)  * 0.12;  // halo
  col += uSunColor * pow(s, 3.0)   * 0.025; // faint wide glow

  gl_FragColor = vec4(col, 1.0);
}
`;

function Sky({ stage }: { stage: Stage }) {
  const mat = useRef<THREE.ShaderMaterial>(null);
  const sunDir = useMemo(() => new THREE.Vector3(), []);
  const uniforms = useMemo(
    () => ({
      uTop: { value: stage.skyTop.clone() },
      uHorizon: { value: stage.skyHorizon.clone() },
      uSunColor: { value: stage.sunColor.clone() },
      uSunDir: { value: new THREE.Vector3() },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useFrame(() => {
    const m = mat.current;
    if (!m) return;
    const u = m.uniforms;
    u.uTop.value.copy(stage.skyTop);
    u.uHorizon.value.copy(stage.skyHorizon);
    u.uSunColor.value.copy(stage.sunColor);
    u.uSunDir.value.copy(sunDir.copy(stage.sunPosition).normalize());
  });

  return (
    <mesh frustumCulled={false}>
      <sphereGeometry args={[420, 40, 40]} />
      <shaderMaterial
        ref={mat}
        vertexShader={SKY_VERT}
        fragmentShader={SKY_FRAG}
        uniforms={uniforms}
        side={THREE.BackSide}
        depthWrite={false}
      />
    </mesh>
  );
}

/* =============================================================================
 *  Sun mesh  —  the bright body that drives God Rays (kept out of tone-mapping)
 * ========================================================================== */

function Sun({ stage, onReady }: { stage: Stage; onReady: (m: THREE.Mesh | null) => void }) {
  return (
    <mesh ref={onReady} position={stage.sunPosition.toArray()} frustumCulled={false}>
      <sphereGeometry args={[4.5, 32, 32]} />
      {/* toneMapped=false keeps the disk above Bloom's luminance threshold */}
      <meshBasicMaterial color={stage.sunColor.clone()} toneMapped={false} />
    </mesh>
  );
}

/* Scene lighting so the standard-material trees & palms read with form. */
function Lights({ stage }: { stage: Stage }) {
  const dir = useRef<THREE.DirectionalLight>(null);
  useFrame(() => {
    const d = dir.current;
    if (!d) return;
    d.position.copy(stage.sunPosition);
    d.color.copy(stage.sunColor);
  });
  return (
    <>
      <ambientLight intensity={0.75} />
      <directionalLight ref={dir} intensity={1.15} />
    </>
  );
}

/* =============================================================================
 *  StageMorph  —  advances time, lerps biomes, drives the sun & camera parallax
 * ========================================================================== */

function StageMorph({
  biome,
  stage,
  sun,
}: {
  biome: BiomeKey;
  stage: Stage;
  sun: THREE.Mesh | null;
}) {
  const { camera } = useThree();
  const tmpTarget = useMemo(() => new THREE.Vector3(), []);

  useFrame((state, delta) => {
    // Clamp delta so a backgrounded tab doesn't jump the animation on return.
    stage.time += Math.min(delta, 0.05);

    // Ease the whole world toward the active biome preset.
    lerpStage(stage, BIOME_RUNTIME[biome], DIVINE_CONFIG.biomeMorphEase);

    // Keep the God-Rays sun body in sync with the morphing sun.
    if (sun) {
      sun.position.copy(stage.sunPosition);
      (sun.material as THREE.MeshBasicMaterial).color.copy(stage.sunColor);
    }

    // Ease the camera to the active biome's framing, with a gentle parallax.
    const px = stage.cameraPos.x + state.pointer.x * 2.2;
    const py = stage.cameraPos.y + state.pointer.y * 1.1;
    camera.position.x += (px - camera.position.x) * 0.04;
    camera.position.y += (py - camera.position.y) * 0.04;
    camera.position.z += (stage.cameraPos.z - camera.position.z) * 0.04;
    camera.lookAt(tmpTarget.copy(stage.cameraTarget));
  });

  return null;
}

/* =============================================================================
 *  Post-processing  —  God Rays + Bloom + Vignette
 * ========================================================================== */

function Effects({ sun }: { sun: THREE.Mesh }) {
  return (
    <EffectComposer multisampling={4}>
      <GodRays
        sun={sun}
        blendFunction={BlendFunction.SCREEN}
        samples={50}
        density={0.86}
        decay={0.9}
        weight={0.3}
        exposure={0.3}
        clampMax={0.85}
        kernelSize={KernelSize.SMALL}
        blur={true}
      />
      <Bloom intensity={0.4} luminanceThreshold={0.82} luminanceSmoothing={0.1} mipmapBlur />
      <Vignette eskil={false} offset={0.3} darkness={0.5} />
    </EffectComposer>
  );
}

/* =============================================================================
 *  Loading veil + WebGL error boundary  —  graceful, elegant fallbacks
 * ========================================================================== */

function LoadingVeil({ show }: { show: boolean }) {
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 z-10 flex items-center justify-center transition-opacity duration-1000 ${
        show ? "opacity-100" : "opacity-0"
      }`}
      style={{ background: "radial-gradient(120% 120% at 50% 30%, #0d2233 0%, #07121c 60%, #050b12 100%)" }}
    >
      <div className="flex flex-col items-center gap-4">
        <span className="h-10 w-10 animate-spin rounded-full border-2 border-white/15 border-t-white/80" />
        <span className="text-sm font-medium tracking-[0.25em] text-white/70">ENTERING THE DIVINE</span>
      </div>
    </div>
  );
}

class CanvasErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) {
      // WebGL unavailable → a calm gradient so the UI above stays readable.
      return (
        <div
          className="absolute inset-0"
          style={{ background: "linear-gradient(180deg,#1f4e7a 0%,#2f7da0 45%,#bfe3d6 100%)" }}
        />
      );
    }
    return this.props.children;
  }
}

/* =============================================================================
 *  DivineCanvas  —  the exported full-screen background canvas
 * ========================================================================== */

export interface DivineCanvasProps {
  /** Active biome section — drives the morphing world. */
  biome: BiomeKey;
  className?: string;
}

export default function DivineCanvas({ biome, className = "" }: DivineCanvasProps) {
  // One Stage for the lifetime of the canvas, seeded from the first biome.
  const stage = useMemo(() => createStage(biome), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [sun, setSun] = useState<THREE.Mesh | null>(null);
  const [ready, setReady] = useState(false);

  return (
    <div className={`absolute inset-0 ${className}`}>
      <CanvasErrorBoundary>
        <Canvas
          dpr={[1, 2]}
          camera={{ position: [0, 6, 26], fov: 50, near: 0.1, far: 800 }}
          gl={{ antialias: true, powerPreference: "high-performance" }}
          onCreated={({ gl }) => {
            gl.toneMapping = THREE.ACESFilmicToneMapping;
            gl.toneMappingExposure = 0.98;
            // Reveal once the context is live and the first frame is queued.
            requestAnimationFrame(() => setReady(true));
          }}
        >
          <Suspense fallback={null}>
            <StageMorph biome={biome} stage={stage} sun={sun} />
            <Lights stage={stage} />
            <Sky stage={stage} />
            <Sun stage={stage} onReady={setSun} />
            <Landscape stage={stage} biome={biome} />
            {sun && <Effects sun={sun} />}
          </Suspense>
        </Canvas>
      </CanvasErrorBoundary>

      <LoadingVeil show={!ready} />
    </div>
  );
}
