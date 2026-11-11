// @vitest-environment jsdom
import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import FloatingProfile from './FloatingProfile';
import { profile } from '../../test/setup';
import { ProfileSummary } from '../../types';
const summary: ProfileSummary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 1, total_count: 2, mastery_score: 0, metric_kind: 'assessed_mean', assessment_coverage: 0.5 };
const mousePointer = (element: Element, type: string) => { const event = new MouseEvent(type, { bubbles: true }); Object.defineProperty(event, 'pointerType', { value: 'mouse' }); fireEvent(element, event); };
const props = { profile: profile(), summary, activeNodeId: null, sessionId: 's1', generation: 1, hostRef: createRef<HTMLElement>(), topbarRef: createRef<HTMLElement>(), composerRef: createRef<HTMLElement>(), ratio: .5, savePreference: vi.fn() };
it('closes a hovered card on Escape from body and reopens after leaving', () => {
  const save = vi.fn(); render(<FloatingProfile {...props} savePreference={save} />);
  const trigger = screen.getByRole('button', { name: '学习画像' }); const container = trigger.parentElement!;
  expect(document.activeElement).toBe(document.body);
  mousePointer(container, 'pointerover'); expect(trigger.getAttribute('aria-expanded')).toBe('true');
  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(trigger.getAttribute('aria-expanded')).toBe('false'); expect(document.activeElement).toBe(trigger);
  expect(save).not.toHaveBeenCalled();
  mousePointer(container, 'pointerout'); mousePointer(container, 'pointerover'); expect(trigger.getAttribute('aria-expanded')).toBe('true');
});
it('leaves Escape to other inputs, composition and supported overlays', () => {
  render(<FloatingProfile {...props} />); const trigger = screen.getByRole('button', { name: '学习画像' });
  mousePointer(trigger.parentElement!, 'pointerover');
  const input = document.createElement('input'); document.body.append(input); input.focus();
  const send = (target: Element, options: KeyboardEventInit = {}) => { const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Escape', ...options }); fireEvent(target, event); return event; };
  expect(send(input).defaultPrevented).toBe(false); expect(document.activeElement).toBe(input);
  expect(send(document.body, { isComposing: true }).defaultPrevented).toBe(false);
  const prevented = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Escape' }); prevented.preventDefault(); fireEvent(document.body, prevented);
  for (const markup of ['<dialog open></dialog>', '<div role="dialog"></div>', '<aside class="workspace-sidebar" data-mode="mobile"></aside>']) {
    const overlay = document.createElement('div'); overlay.innerHTML = markup; document.body.append(overlay);
    expect(send(document.body).defaultPrevented).toBe(false); expect(document.activeElement).toBe(input); overlay.remove();
  }
  expect(trigger.getAttribute('aria-expanded')).toBe('true'); input.remove();
});
it('cleans the Escape listener on session change and unmount', () => {
  const { rerender, unmount } = render(<FloatingProfile {...props} />); const trigger = screen.getByRole('button', { name: '学习画像' });
  mousePointer(trigger.parentElement!, 'pointerover'); rerender(<FloatingProfile {...props} sessionId="s2" generation={2} />);
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Escape' }); fireEvent(document.body, event);
  expect(event.defaultPrevented).toBe(false); expect(trigger.getAttribute('aria-expanded')).toBe('false');
  mousePointer(trigger.parentElement!, 'pointerover'); fireEvent.keyDown(document.body, { key: 'Escape' }); expect(trigger.getAttribute('aria-expanded')).toBe('false');
  unmount(); const after = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Escape' }); fireEvent(document.body, after); expect(after.defaultPrevented).toBe(false);
});
it('shows the actual zero score and coverage and can reopen after Escape', () => {
  render(<FloatingProfile {...props} />);
  const trigger = screen.getByRole('button', { name: '学习画像' });
  expect(screen.getByText('0%')).toBeTruthy();
  mousePointer(trigger.parentElement!, 'pointerover');
  expect(screen.getByText(/评估覆盖 1 \/ 2/)).toBeTruthy();
  fireEvent.keyDown(trigger, { key: 'Escape' });
  expect(trigger.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(trigger);
  expect(trigger.getAttribute('aria-expanded')).toBe('true');
});

it('shows unavailable on revision mismatch and does not invent a score', () => {
  render(<FloatingProfile {...props} summary={{ ...summary, profile_revision: 2 }} />);
  expect(screen.getByText('画像暂不可用')).toBeTruthy();
  expect(screen.queryByText('0%')).toBeNull();
});
it('shows pending assessment rather than zero and links the current session', () => {
  render(<FloatingProfile {...props} summary={{ ...summary, mastery_score: null }} />);
  expect(screen.getByText('待评估')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '学习画像' }));
  expect(screen.getByRole('link', { name: '查看完整画像' }).getAttribute('href')).toBe('/profile?profile_id=p1&session_id=s1');
});

it('commits only a completed drag beyond four pixels and cancels on session change', () => {
  const save = vi.fn(); const host = document.createElement('div'); const bar = document.createElement('div'); const composer = document.createElement('div');
  host.getBoundingClientRect = () => ({ top: 0, bottom: 500, height: 500 } as DOMRect);
  bar.getBoundingClientRect = () => ({ bottom: 40 } as DOMRect);
  composer.getBoundingClientRect = () => ({ top: 450 } as DOMRect);
  const current = { ...props, hostRef: { current: host }, topbarRef: { current: bar }, composerRef: { current: composer }, savePreference: save };
  const { rerender } = render(<FloatingProfile {...current} />);
  const handle = screen.getByRole('button', { name: '调整画像位置' });
  const capture = vi.fn(); const release = vi.fn();
  handle.setPointerCapture = capture; handle.hasPointerCapture = () => true; handle.releasePointerCapture = release;
  const pointer = (type: string, y: number) => { const event = new MouseEvent(type, { bubbles: true, button: 0, clientY: y }); Object.defineProperties(event, { pointerId: { value: 7 }, isPrimary: { value: true } }); fireEvent(handle, event); };
  pointer('pointerdown', 100); pointer('pointermove', 104); pointer('pointerup', 104);
  expect(save).not.toHaveBeenCalled();
  pointer('pointerdown', 100); pointer('pointermove', 105); pointer('pointerup', 105);
  expect(save).toHaveBeenCalledTimes(1); expect(capture).toHaveBeenCalledTimes(2); expect(release).toHaveBeenCalledTimes(2);
  pointer('pointerdown', 100); pointer('pointermove', 120);
  rerender(<FloatingProfile {...current} sessionId="s2" />);
  pointer('pointerup', 120); expect(save).toHaveBeenCalledTimes(1); expect(release).toHaveBeenCalledTimes(3);
});
it('moves twelve pixels by keyboard within the measured travel', () => {
  const save = vi.fn(); const host = document.createElement('div'); const bar = document.createElement('div'); const composer = document.createElement('div');
  host.getBoundingClientRect = () => ({ top: 0, bottom: 500 } as DOMRect); bar.getBoundingClientRect = () => ({ bottom: 40 } as DOMRect); composer.getBoundingClientRect = () => ({ top: 450 } as DOMRect);
  render(<FloatingProfile {...props} hostRef={{ current: host }} topbarRef={{ current: bar }} composerRef={{ current: composer }} savePreference={save} />);
  fireEvent.keyDown(screen.getByRole('button', { name: '调整画像位置' }), { key: 'ArrowDown' });
  expect(save).toHaveBeenCalledWith(.5 + 12 / 394);
});
it('suppresses the post-drag click for 350 ms and permits a later activation', () => {
  const now = vi.spyOn(performance, 'now'); now.mockReturnValue(1000);
  const host = document.createElement('div'), bar = document.createElement('div'), composer = document.createElement('div');
  host.getBoundingClientRect = () => ({ top: 0, bottom: 500 } as DOMRect); bar.getBoundingClientRect = () => ({ bottom: 40 } as DOMRect); composer.getBoundingClientRect = () => ({ top: 450 } as DOMRect);
  render(<FloatingProfile {...props} hostRef={{ current: host }} topbarRef={{ current: bar }} composerRef={{ current: composer }} />);
  const handle = screen.getByRole('button', { name: '调整画像位置' }); const trigger = screen.getByRole('button', { name: '学习画像' });
  const pointer = (type: string, y: number) => { const event = new MouseEvent(type, { bubbles: true, button: 0, clientY: y }); Object.defineProperties(event, { pointerId: { value: 7 }, isPrimary: { value: true } }); fireEvent(handle, event); };
  pointer('pointerdown', 100); pointer('pointermove', 110); pointer('pointerup', 110);
  now.mockReturnValue(1349); fireEvent.click(trigger); expect(trigger.getAttribute('aria-expanded')).toBe('false');
  now.mockReturnValue(1350); fireEvent.click(trigger); expect(trigger.getAttribute('aria-expanded')).toBe('true');
});
it('cancels pointer movement without saving and permits Escape followed by re-entry', () => {
  const save = vi.fn(); const host = document.createElement('div'), bar = document.createElement('div'), composer = document.createElement('div');
  host.getBoundingClientRect = () => ({ top: 0, bottom: 500 } as DOMRect); bar.getBoundingClientRect = () => ({ bottom: 40 } as DOMRect); composer.getBoundingClientRect = () => ({ top: 450 } as DOMRect);
  render(<FloatingProfile {...props} hostRef={{ current: host }} topbarRef={{ current: bar }} composerRef={{ current: composer }} savePreference={save} />);
  const handle = screen.getByRole('button', { name: '调整画像位置' }); const trigger = screen.getByRole('button', { name: '学习画像' }); const container = trigger.parentElement!;
  const pointer = (type: string, y: number) => { const event = new MouseEvent(type, { bubbles: true, button: 0, clientY: y }); Object.defineProperties(event, { pointerId: { value: 7 }, isPrimary: { value: true } }); fireEvent(handle, event); };
  pointer('pointerdown', 100); pointer('pointermove', 120); pointer('pointercancel', 120); pointer('pointerup', 120); expect(save).not.toHaveBeenCalled();
  mousePointer(container, 'pointerover'); fireEvent.keyDown(trigger, { key: 'Escape' }); expect(trigger.getAttribute('aria-expanded')).toBe('false');
  mousePointer(container, 'pointerout'); mousePointer(container, 'pointerover'); expect(trigger.getAttribute('aria-expanded')).toBe('true');
});
it('touch activation opens even when the browser focuses the button before click', () => {
  render(<FloatingProfile {...props} />); const trigger = screen.getByRole('button', { name: '学习画像' });
  const event = new MouseEvent('pointerdown', { bubbles: true }); Object.defineProperties(event, { pointerId: { value: 1 }, isPrimary: { value: true }, pointerType: { value: 'touch' } });
  fireEvent(trigger, event); fireEvent.focus(trigger); fireEvent.click(trigger);
  expect(trigger.getAttribute('aria-expanded')).toBe('true');
});
