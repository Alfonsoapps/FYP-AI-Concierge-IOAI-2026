"use client";

/**
 * page.tsx — Root page for the IOAI 2027 AI Concierge.
 *
 * CRITICAL LAYOUT FIX:
 * The previous layout caused a 0px-height Canvas collapse because the parent
 * <main> did not establish an explicit height context. By using `h-screen` with
 * `overflow-hidden` on a `relative` wrapper, we create a strict full-screen
 * stacking context:
 *   - AvatarView (z-0): fills the entire background with the 3D scene.
 *   - ChatInterface (z-10+): floats on top as a fixed UI overlay.
 *
 * Both children are rendered as direct siblings inside the wrapper.
 */

import dynamic from "next/dynamic";
import ChatInterface from "@/components/ChatInterface";

// Dynamic import with SSR disabled — Three.js/WebGL requires browser APIs
const AvatarView = dynamic(() => import("@/components/AvatarView"), {
  ssr: false,
});

export default function Home() {
  return (
    /**
     * CRITICAL FIX: strict full-screen relative wrapper.
     * - `relative` establishes the positioning context for absolute children.
     * - `w-full h-screen` guarantees the wrapper spans the full viewport.
     * - `overflow-hidden` prevents any scroll bleed from 3D canvas.
     * - `bg-gray-900` provides a dark fallback while the 3D scene loads.
     */
    <main className="relative w-full h-screen overflow-hidden bg-gray-900">
      {/* 3D Avatar Scene — fills background at z-0 */}
      <AvatarView />

      {/* Chat UI — floats on top at z-20 */}
      <ChatInterface />
    </main>
  );
}
