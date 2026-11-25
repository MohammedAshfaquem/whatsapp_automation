import { CSSProperties, ReactNode, useId, useLayoutEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface ModalProps { title: string; onClose: () => void; children: ReactNode; maxWidth?: string; zIndex?: number; className?: string; style?: CSSProperties; }
const stack: symbol[] = [];
let previousOverflow = '';
const focusableSelector = 'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';
export function Modal({ title, onClose, children, maxWidth, zIndex, className = '', style }: ModalProps) {
 const titleId = useId();
 const token = useRef(Symbol('modal'));
 const box = useRef<HTMLDivElement>(null);
 const close = useRef(onClose); close.current = onClose;
 const topmost = () => stack[stack.length - 1] === token.current;
 useLayoutEffect(() => {
  const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  if (!stack.length) { previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; }
  stack.push(token.current);
  const focusables = () => Array.from(box.current?.querySelectorAll<HTMLElement>(focusableSelector) || []).filter(el => !el.hidden && el.getAttribute('aria-hidden') !== 'true');
  (focusables()[0] || box.current)?.focus();
  const keydown = (event: KeyboardEvent) => {
   if (!topmost()) return;
   if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close.current(); }
   if (event.key === 'Tab') {
    const items = focusables(), first = items[0], last = items[items.length - 1];
    if (!first) { event.preventDefault(); box.current?.focus(); }
    else if (event.shiftKey && (document.activeElement === first || !box.current?.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || !box.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
   }
  };
  document.addEventListener('keydown', keydown);
  return () => {
   const wasTop = topmost(); const index = stack.indexOf(token.current); if (index !== -1) stack.splice(index, 1);
   document.removeEventListener('keydown', keydown);
   if (!stack.length) document.body.style.overflow = previousOverflow;
   if (wasTop && returnFocus?.isConnected) returnFocus.focus();
  };
 }, []);
 return <div className="modal-backdrop" style={{ zIndex }} onClick={event => { if (event.target === event.currentTarget && topmost()) close.current(); }}>
  <div ref={box} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className={`modal-box ${className}`} style={{ maxHeight: '90vh', overflowY: 'auto', ...style, ...(maxWidth ? { maxWidth } : {}) }} onClick={event => event.stopPropagation()}>
   <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', padding: '1.25rem', borderBottom: "1px solid var(--border)", flexShrink: 0, position: 'sticky', top: 0, backgroundColor: "var(--bg-card)", zIndex: 1 }}>
    <h2 id={titleId} style={{ fontSize: '1.15rem', fontWeight: 700, color: "var(--text-main)", margin: 0 }}>{title}</h2>
    <button type="button" className="btn btn-secondary btn-sm" aria-label={`Close ${title}`} title={`Close ${title}`} onClick={() => { if (topmost()) close.current(); }} style={{ flexShrink: 0, padding: '.5rem' }}><X size={20} aria-hidden="true" /></button>
   </div>
   {children}
  </div>
 </div>;
}
export default Modal;


