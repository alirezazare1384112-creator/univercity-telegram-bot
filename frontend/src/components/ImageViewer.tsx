import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

const MIN_SCALE = 1;
const MAX_SCALE = 6;
const TAP_MS = 300;
const TAP_PX = 14;
const DOUBLE_MS = 300;
const EDGE = 48;
const ZOOM_IN_SCALE = 2.5;
const ANIM_MS = 220;

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

function clampAxis(move: number, imageSize: number, viewport: number): number {
  const lo = EDGE - viewport / 2 - imageSize / 2;
  const hi = viewport / 2 - EDGE + imageSize / 2;
  if (lo > hi) return 0;
  return clamp(move, lo, hi);
}

interface Gesture {
  mode: "none" | "pan" | "pinch";
  startX: number;
  startY: number;
  startTx: number;
  startTy: number;
  startScale: number;
  dist: number;
  midX: number;
  midY: number;
  beganAt: number;
  moved: boolean;
}

const IDLE_GESTURE: Gesture = {
  mode: "none",
  startX: 0,
  startY: 0,
  startTx: 0,
  startTy: 0,
  startScale: 1,
  dist: 1,
  midX: 0,
  midY: 0,
  beganAt: 0,
  moved: false,
};

interface Props {
  url: string;
  alt: string;
  onClose: () => void;
}

export default function ImageViewer({ url, alt, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const pointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const gesture = useRef<Gesture>({ ...IDLE_GESTURE });
  const lastTap = useRef(0);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [anim, setAnim] = useState(false);

  const latest = useRef({ scale: 1, tx: 0, ty: 0 });
  latest.current = { scale, tx, ty };

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const applyClamp = (targetScale: number, x: number, y: number) => {
    const img = imgRef.current;
    if (!img) return { x, y };
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    return {
      x: clampAxis(x, img.offsetWidth * targetScale, vw),
      y: clampAxis(y, img.offsetHeight * targetScale, vh),
    };
  };

  const animateTo = (targetScale: number, x: number, y: number) => {
    setAnim(true);
    setScale(targetScale);
    setTx(x);
    setTy(y);
    window.setTimeout(() => setAnim(false), ANIM_MS);
  };

  const zoomAbout = (px: number, py: number, targetScale: number, animate: boolean) => {
    const state = latest.current;
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    let nx = 0;
    let ny = 0;
    if (targetScale > MIN_SCALE) {
      const qx = (px - cx - state.tx) / state.scale;
      const qy = (py - cy - state.ty) / state.scale;
      const next = applyClamp(
        targetScale,
        px - cx - targetScale * qx,
        py - cy - targetScale * qy,
      );
      nx = next.x;
      ny = next.y;
    }
    if (animate) {
      animateTo(targetScale, nx, ny);
      return;
    }
    setScale(targetScale);
    setTx(nx);
    setTy(ny);
  };

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const state = latest.current;
      const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
      const target = clamp(state.scale * factor, MIN_SCALE, MAX_SCALE);
      if (target === state.scale) return;
      zoomAbout(event.clientX, event.clientY, target, false);
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      /* pointer already gone */
    }
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (!ready) return;
    const points = [...pointers.current.values()];
    if (points.length === 1) {
      const state = latest.current;
      gesture.current = {
        ...IDLE_GESTURE,
        mode: "pan",
        startX: points[0].x,
        startY: points[0].y,
        startTx: state.tx,
        startTy: state.ty,
        startScale: state.scale,
        beganAt: performance.now(),
      };
    } else if (points.length === 2) {
      const state = latest.current;
      const [a, b] = points;
      gesture.current = {
        ...IDLE_GESTURE,
        mode: "pinch",
        startTx: state.tx,
        startTy: state.ty,
        startScale: state.scale,
        dist: Math.max(Math.hypot(a.x - b.x, a.y - b.y), 1),
        midX: (a.x + b.x) / 2,
        midY: (a.y + b.y) / 2,
        beganAt: performance.now(),
        moved: true,
      };
    }
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!pointers.current.has(event.pointerId)) return;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (!ready) return;
    const current = gesture.current;
    const points = [...pointers.current.values()];

    if (current.mode === "pinch" && points.length >= 2) {
      const [a, b] = points;
      const dist = Math.max(Math.hypot(a.x - b.x, a.y - b.y), 1);
      const midX = (a.x + b.x) / 2;
      const midY = (a.y + b.y) / 2;
      const nextScale = clamp((current.startScale * dist) / current.dist, MIN_SCALE, MAX_SCALE);
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      const qx = (current.midX - cx - current.startTx) / current.startScale;
      const qy = (current.midY - cy - current.startTy) / current.startScale;
      const next = applyClamp(nextScale, midX - cx - nextScale * qx, midY - cy - nextScale * qy);
      setScale(nextScale);
      setTx(next.x);
      setTy(next.y);
      return;
    }

    if (current.mode === "pan" && points.length === 1) {
      const dx = points[0].x - current.startX;
      const dy = points[0].y - current.startY;
      if (Math.hypot(dx, dy) > TAP_PX) current.moved = true;
      if (!current.moved) return;
      const next = applyClamp(current.startScale, current.startTx + dx, current.startTy + dy);
      setTx(next.x);
      setTy(next.y);
    }
  };

  const onPointerEnd = (event: ReactPointerEvent<HTMLDivElement>) => {
    pointers.current.delete(event.pointerId);
    const current = gesture.current;
    const remaining = [...pointers.current.values()];

    if (remaining.length === 1 && current.mode === "pinch") {
      const state = latest.current;
      gesture.current = {
        ...IDLE_GESTURE,
        mode: "pan",
        startX: remaining[0].x,
        startY: remaining[0].y,
        startTx: state.tx,
        startTy: state.ty,
        startScale: state.scale,
        beganAt: performance.now(),
        moved: true,
      };
      return;
    }

    if (remaining.length > 0) return;

    if (
      ready &&
      current.mode === "pan" &&
      !current.moved &&
      performance.now() - current.beganAt < TAP_MS
    ) {
      const now = performance.now();
      if (now - lastTap.current < DOUBLE_MS) {
        lastTap.current = 0;
        const state = latest.current;
        if (state.scale > 1.05) zoomAbout(event.clientX, event.clientY, MIN_SCALE, true);
        else zoomAbout(event.clientX, event.clientY, ZOOM_IN_SCALE, true);
      } else {
        lastTap.current = now;
      }
    }
    gesture.current = { ...IDLE_GESTURE };
  };

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-50 flex touch-none select-none items-center justify-center overflow-hidden bg-black"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onContextMenu={(e) => e.preventDefault()}
    >
      {!ready && !failed && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/80">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-white/30 border-t-white" />
          <p className="text-xs">در حال بارگذاری تصویر…</p>
        </div>
      )}

      {failed ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center text-white/80">
          <p className="text-sm">نمایش تصویر ممکن نشد.</p>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-white/15 px-4 py-2 text-sm font-bold text-white active:opacity-70"
          >
            بستن
          </button>
        </div>
      ) : (
        <img
          ref={imgRef}
          src={url}
          alt={alt}
          draggable={false}
          onLoad={() => setReady(true)}
          onError={() => setFailed(true)}
          className={`max-h-full max-w-full object-contain ${ready ? "" : "opacity-0"}`}
          style={{
            transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
            transition: anim ? `transform ${ANIM_MS}ms ease` : "none",
            touchAction: "none",
            WebkitTouchCallout: "none",
          }}
        />
      )}

      <button
        type="button"
        aria-label="بستن"
        onClick={onClose}
        className="absolute left-3 top-3 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-black/50 text-lg text-white backdrop-blur active:opacity-70"
      >
        ✕
      </button>

      {ready && !failed && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center gap-1.5 p-4 pb-[calc(env(safe-area-inset-bottom)+16px)]">
          <p className="max-w-full truncate rounded-full bg-black/50 px-3 py-1 text-xs text-white">
            {alt}
          </p>
          {scale <= 1.01 && (
            <p className="rounded-full bg-black/50 px-3 py-1 text-[11px] text-white/80">
              دو انگشت برای زوم • دو ضربه برای بزرگ‌نمایی
            </p>
          )}
        </div>
      )}
    </div>
  );
}
