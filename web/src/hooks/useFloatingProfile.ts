import { useCallback, useLayoutEffect, useRef, useState, type RefObject, type PointerEvent as ReactPointerEvent, type KeyboardEvent as ReactKeyboardEvent, type FocusEvent as ReactFocusEvent, type MouseEvent as ReactMouseEvent } from 'react';

export interface FloatingBounds { minimumTop: number; maximumTop: number; availableHeight: number; travel: number }
export function measureFloatingBounds(host: DOMRect, topbar: DOMRect, composer: DOMRect, height: number): FloatingBounds {
  const minimumTop = Math.max(host.top, topbar.bottom) - host.top + 8;
  const availableHeight = Math.max(0, Math.min(host.bottom, composer.top) - host.top - 8 - minimumTop);
  const travel = Math.max(0, availableHeight - height);
  return { minimumTop, maximumTop: minimumTop + travel, availableHeight, travel };
}
export function normalizeProgressRatio(value: unknown): number { return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : .5; }
export function ratioToTop(ratio: number, bounds: FloatingBounds): number { return bounds.minimumTop + normalizeProgressRatio(ratio) * bounds.travel; }
export function topToRatio(top: number, bounds: FloatingBounds, previous: number): number { return bounds.travel ? normalizeProgressRatio((top - bounds.minimumTop) / bounds.travel) : normalizeProgressRatio(previous); }
interface Options { hostRef: RefObject<HTMLElement>; topbarRef: RefObject<HTMLElement>; composerRef: RefObject<HTMLElement>; ratio: number; sessionId: string; generation: number; savePreference: (value: number) => Promise<boolean> | void }
interface Drag { pointerId: number; element: HTMLElement; startY: number; startTop: number; startRatio: number; moved: boolean; currentRatio: number }
export function useFloatingProfile({ hostRef, topbarRef, composerRef, ratio, sessionId, generation, savePreference }: Options) {
  const containerRef = useRef<HTMLDivElement>(null); const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false); const [dragging, setDragging] = useState(false);
  const [bounds, setBounds] = useState<FloatingBounds | null>(null); const [dragRatio, setDragRatio] = useState<number | null>(null);
  const pointerActivation = useRef(false); const drag = useRef<Drag | null>(null); const dismissed = useRef(false); const hover = useRef(false); const touchLock = useRef(false); const suppressUntil = useRef(0);
  const currentRatio = dragRatio ?? normalizeProgressRatio(ratio);
  const measure = useCallback(() => {
    const host = hostRef.current, bar = topbarRef.current, composer = composerRef.current, card = containerRef.current;
    if (!host || !bar || !composer || !card) return;
    const next = measureFloatingBounds(host.getBoundingClientRect(), bar.getBoundingClientRect(), composer.getBoundingClientRect(), card.getBoundingClientRect().height);
    setBounds(old => old && Object.keys(next).every(key => old[key as keyof FloatingBounds] === next[key as keyof FloatingBounds]) ? old : next);
  }, [hostRef, topbarRef, composerRef]);
  const cancel = useCallback(() => {
    const active = drag.current; drag.current = null;
    if (active?.element.hasPointerCapture?.(active.pointerId)) active.element.releasePointerCapture(active.pointerId);
    setDragRatio(null); setDragging(false);
  }, []);
  useLayoutEffect(() => { cancel(); pointerActivation.current = false; setOpen(false); dismissed.current = false; touchLock.current = false; hover.current = false; }, [generation, sessionId, cancel]);
  useLayoutEffect(() => {
    measure(); const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    [hostRef.current, topbarRef.current, composerRef.current, containerRef.current].forEach(node => { if (node) observer?.observe(node); });
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, [measure, open, hostRef, topbarRef, composerRef]);
  useLayoutEffect(() => { const hidden = () => { if (document.hidden) cancel(); }; document.addEventListener('visibilitychange', hidden); return () => { document.removeEventListener('visibilitychange', hidden); cancel(); }; }, [cancel]);
  useLayoutEffect(() => {
    if (!open) return;
    const dismissForEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return;
      if (document.querySelector('dialog[open], [role="dialog"], .workspace-sidebar[data-mode="mobile"]:not([hidden])')) return;
      const target = event.target;
      const inside = target instanceof Node && containerRef.current?.contains(target);
      const pageTarget = target === document.body || target === document.documentElement;
      if (!inside && !(pageTarget && (hover.current || touchLock.current))) return;
      event.preventDefault(); dismissed.current = true; touchLock.current = false; setOpen(false); triggerRef.current?.focus();
    };
    window.addEventListener('keydown', dismissForEscape);
    return () => window.removeEventListener('keydown', dismissForEscape);
  }, [open, sessionId, generation]);
  const onPointerEnter = (event: ReactPointerEvent<HTMLDivElement>) => { if (event.pointerType !== 'mouse') return; hover.current = true; dismissed.current = false; setOpen(true); };
  const onPointerLeave = (event: ReactPointerEvent<HTMLDivElement>) => { if (event.pointerType !== 'mouse') return; hover.current = false; dismissed.current = false; if (!touchLock.current && !drag.current && !containerRef.current?.contains(document.activeElement)) setOpen(false); };
  const onFocus = (event: ReactFocusEvent<HTMLDivElement>) => { if (!event.currentTarget.contains(event.relatedTarget) && !dismissed.current && !pointerActivation.current) setOpen(true); };
  const onBlur = (event: ReactFocusEvent<HTMLDivElement>) => { if (!event.currentTarget.contains(event.relatedTarget)) { dismissed.current = false; if (!hover.current && !touchLock.current && !drag.current) setOpen(false); } };
  const toggle = () => { pointerActivation.current = false; if (performance.now() < suppressUntil.current) return; dismissed.current = false; setOpen(previous => { touchLock.current = !previous; return !previous; }); };
  const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!event.isPrimary || event.button !== 0 || !bounds || drag.current) return;
    drag.current = { pointerId: event.pointerId, element: event.currentTarget, startY: event.clientY, startTop: ratioToTop(currentRatio, bounds), startRatio: currentRatio, moved: false, currentRatio };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const active = drag.current; if (!active || active.pointerId !== event.pointerId || !bounds) return;
    const delta = event.clientY - active.startY; if (!active.moved && Math.abs(delta) <= 4) return;
    active.moved = true; active.currentRatio = topToRatio(active.startTop + delta, bounds, active.startRatio); setDragging(true); setDragRatio(active.currentRatio);
  };
  const onPointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const active = drag.current; if (!active || active.pointerId !== event.pointerId) return;
    if (active.moved) { suppressUntil.current = performance.now() + 350; if (active.currentRatio !== active.startRatio) void savePreference(active.currentRatio); }
    cancel();
  };
  const onPointerCancel = (event: ReactPointerEvent<HTMLButtonElement>) => { if (drag.current?.pointerId === event.pointerId) cancel(); };
  const onHandleKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!bounds || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return;
    event.preventDefault(); const next = topToRatio(ratioToTop(currentRatio, bounds) + (event.key === 'ArrowUp' ? -12 : 12), bounds, currentRatio);
    if (next !== currentRatio) void savePreference(next);
  };
  const onClickCapture = (event: ReactMouseEvent<HTMLDivElement>) => { if (performance.now() < suppressUntil.current) { event.preventDefault(); event.stopPropagation(); } };
  return { containerRef, triggerRef, open, dragging, top: bounds ? ratioToTop(currentRatio, bounds) : undefined, maxHeight: bounds?.availableHeight, containerEvents: { onPointerEnter, onPointerLeave, onFocus, onBlur, onClickCapture }, toggle, onTriggerPointerDown: () => { pointerActivation.current = true; }, onTriggerPointerCancel: () => { pointerActivation.current = false; }, handleEvents: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onLostPointerCapture: onPointerCancel, onKeyDown: onHandleKeyDown } };
}



