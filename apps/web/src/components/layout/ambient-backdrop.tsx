"use client";

import { type CSSProperties, useEffect, useRef } from "react";

export function AmbientBackdrop() {
  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const glow = glowRef.current;
    if (!glow) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    if (reducedMotion.matches || !finePointer.matches) return;

    let frame = 0;
    let targetX = window.innerWidth * 0.72;
    let targetY = window.innerHeight * 0.2;
    let currentX = targetX;
    let currentY = targetY;
    let visible = false;

    const render = () => {
      currentX += (targetX - currentX) * 0.075;
      currentY += (targetY - currentY) * 0.075;
      glow.style.transform = `translate3d(${currentX - 255}px, ${currentY - 255}px, 0)`;
      frame = window.requestAnimationFrame(render);
    };
    const onPointerMove = (event: PointerEvent) => {
      targetX = event.clientX;
      targetY = event.clientY;
      if (!visible) {
        visible = true;
        glow.dataset.visible = "true";
      }
    };
    const onPointerLeave = () => {
      visible = false;
      glow.dataset.visible = "false";
    };

    frame = window.requestAnimationFrame(render);
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    document.documentElement.addEventListener("mouseleave", onPointerLeave);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onPointerMove);
      document.documentElement.removeEventListener("mouseleave", onPointerLeave);
    };
  }, []);

  const dust = Array.from({ length: 48 }, (_, index) => ({
    left: `${(index * 37 + 9) % 97}%`,
    top: `${(index * 61 + 13) % 94}%`,
    width: `${index % 11 === 0 ? 3 : index % 4 === 0 ? 2 : 1}px`,
    height: `${index % 11 === 0 ? 3 : index % 4 === 0 ? 2 : 1}px`,
    animationDelay: `${-(index * 2.7)}s`,
    animationDuration: `${26 + (index * 7) % 25}s`,
    "--dx": `${((index * 17) % 53) - 26}px`,
    "--dy": `${-18 - (index * 13) % 45}px`,
  })) as Array<CSSProperties & Record<"--dx" | "--dy", string>>;

  return <div className="ambient-backdrop" aria-hidden="true">
    <div ref={glowRef} className="ambient-pointer-glow" />
    <div className="ambient-particles">{dust.map((style, index) => <i key={index} style={style} />)}</div>
    <div className="ambient-texture" />
    <div className="ambient-vignette" />
  </div>;
}
