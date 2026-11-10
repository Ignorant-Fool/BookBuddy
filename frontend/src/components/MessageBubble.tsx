import { AnimatePresence, motion } from 'framer-motion';
import {
  BookOpen,
  ChevronDown,
  Copy,
  GitBranch,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Waves,
  Wrench,
  Zap,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AgentStep, HistoryItem } from '../types';
import { cn } from '../lib/cn';
import { toast } from '../lib/toast';

/* ---------------- 用户消息 ---------------- */
export function UserMessage({ item }: { item: HistoryItem }) {
  const [showSignal, setShowSignal] = useState(false);
  const hasSignal = Boolean(item.waveform_image || item.mfcc_image);
  const isVoice = item.duration !== undefined;
  const confidence = Math.round((item.confidence ?? 1) * 100);

  const confidenceTone =
    confidence >= 90
      ? 'text-accent'
      : confidence >= 70
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-[rgb(var(--c-danger))]';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="flex justify-end"
    >
      <div className="max-w-[86%] sm:max-w-[74%]">
        <div className="mb-1.5 flex items-center justify-end gap-2 text-[11px] text-muted">
          {isVoice && item.duration !== undefined && (
            <span className="tabular-nums">{item.duration}s</span>
          )}
          <span className="tabular-nums">{item.time}</span>
          {isVoice && (
            <span className={cn('tabular-nums font-medium', confidenceTone)}>{confidence}%</span>
          )}
        </div>

        <div className="rounded-2xl rounded-br-[6px] border border-line bg-subtle px-4 py-2.5 text-[14.5px] leading-[1.7] text-ink whitespace-pre-wrap">
          {item.question || '（未识别到语音）'}
        </div>

        <div className="mt-1 flex items-center justify-end gap-0.5 opacity-70 transition-opacity hover:opacity-100">
          <button
            onClick={() => {
              void navigator.clipboard.writeText(item.question);
              toast.success('已复制');
            }}
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-subtle hover:text-ink"
            title="复制"
          >
            <Copy size={12.5} />
          </button>
          {hasSignal && (
            <button
              onClick={() => setShowSignal((v) => !v)}
              className={cn(
                'flex items-center gap-1 rounded-lg px-1.5 py-1 text-[11px] transition-colors hover:bg-subtle',
                showSignal ? 'text-accent' : 'text-muted hover:text-ink',
              )}
            >
              <Waves size={12.5} />
              信号分析
            </button>
          )}
        </div>

        <AnimatePresence initial={false}>
          {hasSignal && showSignal && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25 }}
              className="overflow-hidden"
            >
              <div className="mt-2 space-y-2 rounded-2xl border border-line bg-surface p-3">
                {item.waveform_image && (
                  <figure>
                    <figcaption className="mb-1 text-[11px] font-medium text-muted">波形图</figcaption>
                    <img
                      src={`data:image/png;base64,${item.waveform_image}`}
                      alt="音频波形"
                      className="w-full rounded-lg border border-line/60"
                    />
                  </figure>
                )}
                {item.mfcc_image && (
                  <figure>
                    <figcaption className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-muted">
                      MFCC 特征
                      {item.mfcc_shape && item.mfcc_shape[0] > 0 && (
                        <span className="tabular-nums opacity-70">
                          {item.mfcc_shape[0]} × {item.mfcc_shape[1]}
                        </span>
                      )}
                    </figcaption>
                    <img
                      src={`data:image/png;base64,${item.mfcc_image}`}
                      alt="MFCC 热力图"
                      className="w-full rounded-lg border border-line/60"
                    />
                  </figure>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

/* ---------------- AI 消息 ---------------- */
export function AssistantMessage({ item }: { item: HistoryItem }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="flex gap-3"
    >
      <AiAvatar />
      <div className="min-w-0 flex-1 pb-1">
        <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted">
          <span className="font-medium text-ink/80">助手</span>
          {item.model && (
            <span className="inline-flex items-center gap-1 rounded-md bg-subtle px-1.5 py-0.5 font-mono text-[10px] text-muted">
              <Zap size={9.5} className="text-accent" />
              {item.model}
            </span>
          )}
          {item.elapsed !== undefined && <span className="tabular-nums">{item.elapsed}s</span>}
          <span className="tabular-nums">{item.time}</span>
        </div>

        {item.agent_steps && item.agent_steps.length > 0 && (
          <AgentSteps steps={item.agent_steps} />
        )}

        <div className="prose-chat">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.answer}</ReactMarkdown>
        </div>

        <div className="mt-2 flex items-center gap-1 opacity-60 transition-opacity hover:opacity-100">
          <button
            onClick={() => {
              void navigator.clipboard.writeText(item.answer);
              toast.success('已复制回答');
            }}
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-subtle hover:text-ink"
            title="复制回答"
          >
            <Copy size={12.5} />
          </button>
        </div>
      </div>
    </motion.div>
  );
}

export function AiAvatar({ size = 26 }: { size?: number }) {
  return (
    <div
      className="mt-0.5 grid shrink-0 place-items-center rounded-[9px] bg-gradient-to-br from-teal-500 to-emerald-700 text-white shadow-sm"
      style={{ width: size, height: size }}
    >
      <Sparkles size={size * 0.5} strokeWidth={2.2} />
    </div>
  );
}

/* ---------------- Agent 步骤 ---------------- */
const STEP_META: Record<string, { icon: typeof Search; tone: string; label: string }> = {
  analyze: { icon: Search, tone: 'text-sky-600 dark:text-sky-400', label: '分析' },
  classify: { icon: Search, tone: 'text-sky-600 dark:text-sky-400', label: '分析' },
  search: { icon: BookOpen, tone: 'text-indigo-600 dark:text-indigo-400', label: '检索' },
  verify: { icon: ShieldCheck, tone: 'text-emerald-600 dark:text-emerald-400', label: '核验' },
  assess: { icon: ShieldCheck, tone: 'text-emerald-600 dark:text-emerald-400', label: '核验' },
  retry: { icon: RefreshCw, tone: 'text-amber-600 dark:text-amber-400', label: '补检索' },
  cross_check: { icon: GitBranch, tone: 'text-violet-600 dark:text-violet-400', label: '交叉验证' },
  synthesize: { icon: Sparkles, tone: 'text-accent', label: '生成' },
  refine: { icon: Wrench, tone: 'text-rose-600 dark:text-rose-400', label: '自我修正' },
};

export function AgentSteps({ steps }: { steps: AgentStep[] }) {
  const [open, setOpen] = useState(false);
  const counts = useMemo(() => {
    const map = new Map<string, number>();
    steps.forEach((s) => map.set(s.type, (map.get(s.type) ?? 0) + 1));
    return [...map.entries()];
  }, [steps]);

  return (
    <div className="mb-2.5">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'group flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11.5px] transition-colors',
          open
            ? 'border-accent/30 bg-accent-soft text-accent'
            : 'border-line/70 bg-surface text-muted hover:border-accent/25 hover:text-ink',
        )}
      >
        <Sparkles size={11.5} className="text-accent" />
        <span className="font-medium">推理过程</span>
        <span className="tabular-nums opacity-70">{steps.length} 步</span>
        <ChevronDown
          size={12}
          className={cn('transition-transform duration-200', open && 'rotate-180')}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-2 rounded-xl border border-line/70 bg-surface/70 p-3">
              <div className="mb-2 flex flex-wrap gap-1">
                {counts.map(([type, count]) => {
                  const meta = STEP_META[type];
                  return (
                    <span
                      key={type}
                      className="inline-flex items-center gap-1 rounded-md bg-subtle px-1.5 py-0.5 text-[10px] text-muted"
                    >
                      <span className={meta?.tone}>{meta?.label ?? type}</span>
                      <span className="tabular-nums opacity-60">×{count}</span>
                    </span>
                  );
                })}
              </div>

              <ol className="relative space-y-1.5 pl-4">
                <span className="absolute bottom-1.5 left-[5px] top-1.5 w-px bg-line" />
                {steps.map((step, index) => {
                  const meta = STEP_META[step.type];
                  const Icon = meta?.icon ?? Sparkles;
                  return (
                    <li key={index} className="relative flex gap-2 text-[12px] leading-relaxed">
                      <span className="absolute -left-4 top-[5px] h-[7px] w-[7px] rounded-full border border-line bg-subtle" />
                      <Icon size={12} className={cn('mt-[3px] shrink-0', meta?.tone ?? 'text-muted')} />
                      <span className="min-w-0 flex-1 text-muted">{step.content}</span>
                    </li>
                  );
                })}
              </ol>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------------- 思考中 ---------------- */
export function ThinkingBubble() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <AiAvatar />
      <div className="flex flex-1 items-center gap-2.5 pt-1">
        <span className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-accent/70"
              style={{ animationDelay: `${i * 0.16}s` }}
            />
          ))}
        </span>
        <span className="text-[12.5px] text-muted">正在检索并核对证据…</span>
      </div>
    </motion.div>
  );
}
