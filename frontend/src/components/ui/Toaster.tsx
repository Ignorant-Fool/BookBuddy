import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { dismissToast, useToasts, type ToastKind } from '../../lib/toast';

const ICONS: Record<ToastKind, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
};

const TONES: Record<ToastKind, string> = {
  info: 'text-ink',
  success: 'text-accent',
  error: 'text-[rgb(var(--c-danger))]',
  warning: 'text-amber-600 dark:text-amber-400',
};

export function Toaster() {
  const items = useToasts();
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[60] flex flex-col items-center gap-2 px-4">
      <AnimatePresence initial={false}>
        {items.map((item) => {
          const Icon = ICONS[item.kind];
          return (
            <motion.div
              key={item.id}
              layout
              initial={{ opacity: 0, y: -12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 380, damping: 30 }}
              className="pointer-events-auto flex w-full max-w-md items-start gap-2.5 rounded-xl border border-line bg-surface/95 px-3.5 py-2.5 shadow-soft backdrop-blur"
            >
              <Icon size={16} className={`mt-0.5 shrink-0 ${TONES[item.kind]}`} />
              <p className="flex-1 text-[13px] leading-5 text-ink">{item.text}</p>
              <button
                onClick={() => dismissToast(item.id)}
                className="-mr-1 rounded-md p-1 text-muted transition-colors hover:bg-subtle hover:text-ink"
                aria-label="关闭提示"
              >
                <X size={13} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
