"use client";

/**
 * AvatarView.tsx — Full-screen 3D VRM avatar scene for the IOAI 2027 Concierge.
 *
 * CRITICAL LAYOUT FIX:
 * The outermost wrapper uses `absolute inset-0 w-full h-screen z-0` to force
 * a viewport-height rendering surface behind the UI. This prevents the Canvas
 * from collapsing to 0px even if an intermediate percentage height is unresolved.
 *
 * PRESERVED LOGIC (do NOT modify):
 * - VRM bone rotations (T-pose fix)
 * - useFrame animations (breathing, blinking, idle actions, lip-sync)
 * - Memory cleanup (no vrm.dispose())
 * - Html chat bubble rendering
 * - WebSocket speaking event listeners
 */

import * as THREE from "three";
import React, { useRef, useEffect, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Cloud, Html, OrbitControls, Sky, Sparkles, Stars } from "@react-three/drei";
import { VRM, VRMLoaderPlugin, VRMHumanBoneName } from "@pixiv/three-vrm";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// ─── Live Weather-Driven Scene Environment ──────────────────────────────────
// Weather affects only scene atmosphere and lighting; avatar animation and
// skeletal behavior remain fully isolated inside VRMModel.

interface WeatherEnvironmentProps {
  weather: string;
}

function WeatherEnvironment({ weather }: WeatherEnvironmentProps) {
  if (weather === "night") {
    return (
      <>
        <color attach="background" args={["#050510"]} />
        <Stars radius={100} depth={50} count={5000} factor={4} speed={1} />
        <ambientLight intensity={0.4} />
      </>
    );
  }

  if (weather === "rainy") {
    return (
      <>
        <color attach="background" args={["#4a5568"]} />
        <Cloud position={[0, 4, -20]} opacity={0.5} speed={0.4} scale={1.5} />
        <Sparkles
          count={2000}
          scale={[10, 10, 10]}
          position={[0, 4, 0]}
          speed={1.5}
          size={2}
          color="#88ccff"
          opacity={0.6}
        />
        <ambientLight intensity={0.5} />
      </>
    );
  }

  if (weather === "cloudy") {
    return (
      <>
        <color attach="background" args={["#b0c4de"]} />
        <Cloud position={[-4, 4, -8]} opacity={0.6} />
        <Cloud position={[4, 5, -10]} opacity={0.6} />
        <ambientLight intensity={0.7} />
      </>
    );
  }

  // Sunny/default: saturated daylight, atmospheric sky scattering, distant
  // drifting clouds, and warm key/fill lighting for cinematic avatar rendering.
  return (
    <>
      <color attach="background" args={["#4da6ff"]} />
      <Sky
        sunPosition={[2, 1.5, -5]}
        turbidity={0.1}
        rayleigh={0.2}
        mieCoefficient={0.02}
        mieDirectionalG={0.8}
      />
      <Cloud
        position={[-10, 6, -25]}
        speed={0.2}
        opacity={0.6}
        scale={1}
      />
      <Cloud
        position={[12, 8, -30]}
        speed={0.2}
        opacity={0.5}
        scale={1.2}
      />
      <directionalLight
        position={[5, 5, 5]}
        intensity={1.5}
        color="#fffcf2"
      />
      <ambientLight intensity={0.75} color="#ffffff" />
    </>
  );
}

// ─── VRM Model Component ────────────────────────────────────────────────────
// Contains ALL 3D math, bone logic, and animation. Unchanged from original.

interface VRMModelProps {
  avatarUrl: string;
}

function VRMModel({ avatarUrl }: VRMModelProps) {
  const [vrm, setVrm] = useState<VRM | null>(null);
  const vrmRef = useRef<VRM | null>(null);

  // Animation state refs for 60fps performance (no re-renders)
  const blinkTimer = useRef(0);
  const blinkNext = useRef(3 + Math.random() * 3);
  const blinkValue = useRef(0);
  const isSpeaking = useRef(false);
  const lipIndex = useRef(0);
  const lipTimer = useRef(0);
  const actionTimer = useRef(0);
  const actionActive = useRef(false);
  const actionProgress = useRef(0);
  const actionType = useRef(0);
  const actionReturning = useRef(false);

  // Lip-sync viseme cycle order
  const lipShapes = ["aa", "ih", "ou", "ee", "oh"];

  useEffect(() => {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));

    loader.load(avatarUrl, (gltf) => {
      const loadedVrm = gltf.userData.vrm as VRM;
      if (!loadedVrm) return;

      // Force avatar to face the camera
      loadedVrm.scene.rotation.y = 0;

      // Force arms DOWN and slightly bent
      const humanoid = loadedVrm.humanoid;
      if (humanoid) {
        humanoid.getNormalizedBoneNode("leftUpperArm")?.rotation.set(0, 0, -1.2);
        humanoid.getNormalizedBoneNode("rightUpperArm")?.rotation.set(0, 0, 1.2);
        humanoid.getNormalizedBoneNode("leftLowerArm")?.rotation.set(0, 0, 0.15);
        humanoid.getNormalizedBoneNode("rightLowerArm")?.rotation.set(0, 0, -0.15);
        humanoid.getNormalizedBoneNode("leftHand")?.rotation.set(0, -0.2, 0);
        humanoid.getNormalizedBoneNode("rightHand")?.rotation.set(0, 0.2, 0);
      }

      vrmRef.current = loadedVrm;
      setVrm(loadedVrm);
    });

    // ─── Speaking event listeners (for lip-sync) ────────────────────
    const handleStartSpeaking = () => {
      isSpeaking.current = true;
      lipIndex.current = 0;
      lipTimer.current = 0;
    };
    const handleStopSpeaking = () => {
      isSpeaking.current = false;
    };

    window.addEventListener("start-speaking", handleStartSpeaking);
    window.addEventListener("stop-speaking", handleStopSpeaking);

    // ─── Memory Cleanup (NO vrm.dispose()) ──────────────────────────
    return () => {
      window.removeEventListener("start-speaking", handleStartSpeaking);
      window.removeEventListener("stop-speaking", handleStopSpeaking);

      if (vrmRef.current) {
        const vrmScene = vrmRef.current.scene;
        vrmScene.removeFromParent();
        vrmScene.traverse((obj) => {
          if ((obj as THREE.Mesh).geometry) {
            (obj as THREE.Mesh).geometry.dispose();
          }
          if ((obj as THREE.Mesh).material) {
            const mat = (obj as THREE.Mesh).material;
            if (Array.isArray(mat)) {
              mat.forEach((m) => m.dispose());
            } else {
              mat.dispose();
            }
          }
        });
        vrmScene.clear();
      }
    };
  }, [avatarUrl]);

  // ─── useFrame: all animations at 60fps ────────────────────────────────────
  useFrame((_, delta) => {
    const vrm = vrmRef.current;
    if (!vrm) return;

    const time = performance.now() / 1000;

    // --- Chest Breathing: subtle sine oscillation ---
    const chest = vrm.humanoid?.getNormalizedBoneNode(VRMHumanBoneName.Chest);
    if (chest) {
      chest.rotation.x = Math.sin(time * 2) * 0.02;
    }

    // --- Procedural Blinking: random interval 3-6s ---
    blinkTimer.current += delta;
    if (blinkTimer.current >= blinkNext.current) {
      blinkValue.current = 1;
      blinkTimer.current = 0;
      blinkNext.current = 3 + Math.random() * 3;
    }
    blinkValue.current = THREE.MathUtils.lerp(blinkValue.current, 0, 0.3);
    vrm.expressionManager?.setValue("blink", blinkValue.current);

    // --- 30-Second Random Idle Actions ---
    actionTimer.current += delta;
    if (!actionActive.current && actionTimer.current >= 30) {
      actionActive.current = true;
      actionProgress.current = 0;
      actionType.current = Math.floor(Math.random() * 3);
      actionReturning.current = false;
      actionTimer.current = 0;
    }

    if (actionActive.current) {
      actionProgress.current += delta;

      const humanoid = vrm.humanoid;
      if (humanoid) {
        const head = humanoid.getNormalizedBoneNode(VRMHumanBoneName.Head);
        const spine = humanoid.getNormalizedBoneNode(VRMHumanBoneName.Spine);

        // Lerp INTO action over first 4s
        if (actionProgress.current < 4 && !actionReturning.current) {
          const t = Math.min(actionProgress.current / 2, 1);
          if (actionType.current === 0 && head) {
            head.rotation.y = THREE.MathUtils.lerp(0, 0.3, t);
          } else if (actionType.current === 1 && head) {
            head.rotation.x = THREE.MathUtils.lerp(0, -0.15, t);
          } else if (actionType.current === 2 && spine) {
            spine.rotation.y = THREE.MathUtils.lerp(0, 0.1, t);
          }
        } else {
          // Lerp BACK to neutral
          if (!actionReturning.current) {
            actionReturning.current = true;
            actionProgress.current = 0;
          }
          const t = Math.min(actionProgress.current / 2, 1);
          if (actionType.current === 0 && head) {
            head.rotation.y = THREE.MathUtils.lerp(0.3, 0, t);
          } else if (actionType.current === 1 && head) {
            head.rotation.x = THREE.MathUtils.lerp(-0.15, 0, t);
          } else if (actionType.current === 2 && spine) {
            spine.rotation.y = THREE.MathUtils.lerp(0.1, 0, t);
          }
          if (t >= 1) {
            actionActive.current = false;
          }
        }
      }
    }

    // --- Lip-Sync: cycle visemes while speaking ---
    if (isSpeaking.current) {
      lipTimer.current += delta;
      if (lipTimer.current > 0.12) {
        lipTimer.current = 0;
        lipIndex.current = (lipIndex.current + 1) % lipShapes.length;
      }
      // Reset all lip shapes then activate current
      lipShapes.forEach((shape) => {
        vrm.expressionManager?.setValue(shape, 0);
      });
      vrm.expressionManager?.setValue(lipShapes[lipIndex.current], 0.8);
    } else {
      // Silence — all lip shapes to 0
      lipShapes.forEach((shape) => {
        vrm.expressionManager?.setValue(shape, 0);
      });
    }

    // Update VRM internal state (required for expression blending)
    vrm.update(delta);
  });

  return vrm ? <primitive object={vrm.scene} /> : null;
}

// ─── Main AvatarView Component (Default Export) ─────────────────────────────

export default function AvatarView() {
  const [aiMessage, setAiMessage] = useState<string | null>(null);
  const [overlayOpen, setOverlayOpen] = useState(false);
  const [avatarUrl, setAvatarUrl] = useState("/MaleModel.vrm");
  const [weather, setWeather] = useState("sunny");
  const bubbleTimeout = useRef<NodeJS.Timeout | null>(null);

  // Fetch Singapore's current weather once when the scene mounts. The request
  // is safely aborted during unmount, and any network/schema failure falls back
  // to the deterministic sunny environment.
  useEffect(() => {
    const controller = new AbortController();

    const fetchWeather = async () => {
      try {
        const response = await fetch(
          "https://api.open-meteo.com/v1/forecast?latitude=1.3521&longitude=103.8198&current_weather=true",
          { signal: controller.signal },
        );

        if (!response.ok) {
          throw new Error(`Open-Meteo request failed with ${response.status}`);
        }

        const data = (await response.json()) as {
          current_weather?: {
            weathercode?: number;
            is_day?: number;
          };
        };
        const currentWeather = data.current_weather;

        if (!currentWeather) {
          throw new Error("Open-Meteo response omitted current_weather");
        }

        const weatherCode = currentWeather.weathercode ?? 0;

        if (currentWeather.is_day === 0) {
          setWeather("night");
        } else if (weatherCode >= 50) {
          setWeather("rainy");
        } else if (weatherCode >= 1 && weatherCode <= 3) {
          setWeather("cloudy");
        } else {
          setWeather("sunny");
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setWeather("sunny");
        }
      }
    };

    void fetchWeather();

    return () => controller.abort();
  }, []);

  // Listen for AI message events to show the chat bubble in 3D space.
  // The string payload is the canonical event contract; object support keeps
  // compatibility with any already-open client using the previous payload.
  useEffect(() => {
    const handleMessage = (e: Event) => {
      const detail = (
        e as CustomEvent<string | { content?: string }>
      ).detail;
      const content = typeof detail === "string" ? detail : detail?.content;

      if (content) {
        setAiMessage(content);
        // Auto-dismiss bubble after 8 seconds
        if (bubbleTimeout.current) clearTimeout(bubbleTimeout.current);
        bubbleTimeout.current = setTimeout(() => setAiMessage(null), 8000);
      }
    };

    window.addEventListener("ai-message-received", handleMessage);
    return () => {
      window.removeEventListener("ai-message-received", handleMessage);
      if (bubbleTimeout.current) clearTimeout(bubbleTimeout.current);
    };
  }, []);

  return (
    /**
     * CRITICAL LAYOUT FIX:
     * `absolute inset-0` pins this div to all edges of the parent (which has h-screen).
     * `w-full h-screen` forces a viewport-height rendering surface.
     * `z-0` places it behind all UI overlays.
     *
     * This guarantees the Canvas receives a non-zero height and renders
     * the 3D scene correctly, independently of percentage-height inheritance.
     */
    <div className="absolute inset-0 w-full h-screen z-0">
      {/* ─── Settings Dropdown Overlay (Weather / Avatar) ──────────────
       * Uses z-50 so it floats above the Canvas.
       * `pointer-events-auto` ensures clicks register even over the Canvas.
       */}
      <div className="absolute z-50 top-4 right-4 flex gap-4 pointer-events-auto">
        <button
          onClick={() => setOverlayOpen(!overlayOpen)}
          className="bg-white/90 backdrop-blur-sm px-3 py-1.5 rounded-lg text-sm font-medium shadow-md hover:bg-white transition-colors"
        >
          Options ▾
        </button>
        {overlayOpen && (
          <div className="absolute top-10 right-0 bg-white rounded-lg shadow-xl p-3 min-w-[160px]">
            <p className="px-3 pb-2 text-xs font-medium capitalize text-gray-500">
              Singapore: {weather}
            </p>
            <label
              htmlFor="avatar-wardrobe"
              className="block px-3 pt-2 text-xs font-medium text-gray-500"
            >
              Avatar
            </label>
            <select
              id="avatar-wardrobe"
              value={avatarUrl}
              onChange={(event) => setAvatarUrl(event.target.value)}
              className="mt-1 block w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500"
            >
              <option value="/MaleModel.vrm">Male Model</option>
              <option value="/FemaleModel.vrm">Female Model</option>
            </select>
          </div>
        )}
      </div>

      {/* ─── Three.js Canvas ─────────────────────────────────────────────
       * `className="w-full h-full"` ensures the Canvas fills its parent.
       * Camera positioned at [0, 1.4, 2.0] with 45° FOV for optimal avatar framing.
       */}
      <Canvas
        className="w-full h-full"
        camera={{ position: [0, 1.4, 2.0], fov: 45, near: 0.1, far: 1000 }}
        gl={{ antialias: true, alpha: true }}
      >
        {/* Live Singapore weather controls scene color, fog, and lighting. */}
        <WeatherEnvironment weather={weather} />

        {/* VRM Avatar Model */}
        <VRMModel avatarUrl={avatarUrl} />

        {/* Rotate around chest/face level while preserving the fixed framing. */}
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          target={[0, 1.4, 0]}
        />

        {/* ─── Chat Bubble in 3D Space ─────────────────────────────────
         * The fixed world-space anchor sits beside the avatar's face. `w-max`
         * and `max-w-[300px]` create a natural horizontal layout before wrapping,
         * while the explicit z-index range keeps the bubble above WebGL content.
         */}
        {aiMessage && (
          <Html position={[0.7, 1.4, 0]} center zIndexRange={[100, 0]}>
            <div className="bg-white text-gray-800 p-4 rounded-2xl rounded-bl-none shadow-xl border-4 border-blue-400 text-sm font-medium w-max max-w-[300px] pointer-events-none">
              {aiMessage}
            </div>
          </Html>
        )}
      </Canvas>
    </div>
  );
}
