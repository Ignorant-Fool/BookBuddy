/** 轻量 toast：一个模块级 store + 可订阅 hook，避免引入额外依赖。 */
import { useEffect, useState } from 'react';

export type ToastKind = 'info' | 'success' | 'error' | 'warning';

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

let seq = 0;
let items: ToastItem[] = [];
const listeners = new Set<(next: ToastItem[]) => void>();

function emit() {
  const snapshot = [...items];
  listeners.forEach((fn) => fn(snapshot));
}

export function dismissToast(id: number) {
  items = items.filter((item) => item.id !== id);
  emit();
}

export function pushToast(text: string, kind: ToastKind = 'info', ttl = 3800) {
  const id = ++seq;
  items = [...items, { id, kind, text }].slice(-4);
  emit();
  window.setTimeout(() => dismissToast(id), ttl);
  return id;
}

export const toast = {
  info: (text: string) => pushToast(text, 'info'),
  success: (text: string) => pushToast(text, 'success'),
  error: (text: string) => pushToast(text, 'error', 5200),
  warning: (text: string) => pushToast(text, 'warning'),
};

export function useToasts(): ToastItem[] {
  const [state, setState] = useState<ToastItem[]>(items);
  useEffect(() => {
    listeners.add(setState);
    setState([...items]);
    return () => {
      listeners.delete(setState);
    };
  }, []);
  return state;
}
