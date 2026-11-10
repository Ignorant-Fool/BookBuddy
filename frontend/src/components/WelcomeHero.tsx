import { ArrowUpRight, BookOpen, GitBranch, Mic, ShieldCheck } from 'lucide-react';
import { motion } from 'framer-motion';

const SUGGESTIONS = [
  {
    icon: BookOpen,
    title: '人物初见',
    prompt: '林黛玉第一次出场是第几回？',
    hint: '走全文扫描策略定位最早章节',
  },
  {
    icon: GitBranch,
    title: '人物关系',
    prompt: '贾宝玉和薛宝钗是什么关系？',
    hint: '多片段交叉验证后作答',
  },
  {
    icon: ShieldCheck,
    title: '细节考据',
    prompt: '林黛玉的父亲是谁？从事什么官职？',
    hint: '先精排证据，再做事实核查',
  },
  {
    icon: Mic,
    title: '语音提问',
    prompt: '',
    hint: '按住空格直接说话',
  },
];

export function WelcomeHero({
  hasKB,
  onPick,
  onOpenKB,
}: {
  hasKB: boolean;
  onPick: (text: string) => void;
  onOpenKB: () => void;
}) {
  return (
    <div className="relative flex flex-1 items-center justify-center px-5 py-10">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[420px] bg-[radial-gradient(55%_100%_at_50%_0%,rgb(var(--c-accent)/0.09),transparent_72%)]" />

      <div className="relative w-full max-w-[640px]">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/70 px-2.5 py-1 text-[11px] font-medium text-muted backdrop-blur">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            Agentic RAG · 多策略检索 · 自我纠错
          </div>

          <h1 className="text-balance text-[30px] font-semibold leading-[1.25] tracking-[-0.02em] text-ink sm:text-[34px]">
            把书读懂，
            <br className="sm:hidden" />
            从一句提问开始
          </h1>

          <p className="mt-3 max-w-[460px] text-[14px] leading-relaxed text-muted">
            {hasKB
              ? '知识库已就绪。直接提问，或按住空格说一句话——我会先找证据，再作答。'
              : '先把书籍放进知识库，然后就可以用文字或语音向它提问了。'}
          </p>

          {!hasKB && (
            <button
              onClick={onOpenKB}
              className="btn btn-primary group mt-5 h-9 px-4 text-[13px]"
            >
              <BookOpen size={15} />
              上传第一本书
              <ArrowUpRight
                size={14}
                className="transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
              />
            </button>
          )}
        </motion.div>

        <div className="mt-9 flex items-center gap-3">
          <span className="text-[10.5px] font-semibold uppercase tracking-[0.1em] text-muted">
            试试这些
          </span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {SUGGESTIONS.map((item, index) => (
            <motion.button
              key={item.title}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.08 + index * 0.05, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              onClick={() => (item.prompt ? onPick(item.prompt) : onOpenKB())}
              className="group flex items-start gap-3 rounded-2xl border border-line bg-surface/60 p-3.5 text-left backdrop-blur transition-all hover:-translate-y-0.5 hover:border-accent/30 hover:bg-surface hover:shadow-soft"
            >
              <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-[10px] bg-subtle text-muted transition-colors group-hover:bg-accent-soft group-hover:text-accent">
                <item.icon size={15} />
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] font-medium text-ink">{item.title}</span>
                <span className="mt-0.5 block truncate text-[11.5px] text-muted">{item.hint}</span>
              </span>
            </motion.button>
          ))}
        </div>

        <p className="mt-5 flex items-center gap-1.5 text-[11px] text-muted/70">
          <ShieldCheck size={12} className="text-accent/70" />
          回答只基于你上传的书籍，并标注章节出处
        </p>
      </div>
    </div>
  );
}
