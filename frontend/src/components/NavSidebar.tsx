import {
  BookOpen,
  MessageSquare,
  Moon,
  Plus,
  Sparkles,
  Sun,
  Users,
  X,
} from 'lucide-react';
import type { ReactNode } from 'react';
import type { Conversation } from '../types';
import { cn } from '../lib/cn';

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onOpenKB: () => void;
  onOpenChars: () => void;
  dark: boolean;
  onToggleTheme: () => void;
  kbChunks: number;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function NavSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onOpenKB,
  onOpenChars,
  dark,
  onToggleTheme,
  kbChunks,
  mobileOpen,
  onCloseMobile,
}: Props) {
  return (
    <>
      <div
        onClick={onCloseMobile}
        className={cn(
          'fixed inset-0 z-30 bg-black/40 backdrop-blur-[2px] transition-opacity lg:hidden',
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
      />

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[272px] shrink-0 flex-col border-r border-line bg-canvas/95 backdrop-blur-xl',
          'transition-transform duration-300 ease-out lg:static lg:z-auto lg:translate-x-0 lg:bg-canvas',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="px-4 pb-2 pt-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="grid h-9 w-9 place-items-center rounded-[13px] bg-gradient-to-br from-teal-500 to-emerald-700 shadow-sm">
                <BookOpen size={17} className="text-white" strokeWidth={2.2} />
              </div>
              <div className="leading-tight">
                <div className="text-[15px] font-semibold tracking-tight text-ink">BookBuddy</div>
                <div className="text-[11px] text-muted">阅读小助手</div>
              </div>
            </div>
            <button onClick={onCloseMobile} className="icon-btn lg:hidden" aria-label="关闭侧栏">
              <X size={17} />
            </button>
          </div>

          <button
            onClick={onNew}
            className="group mt-5 flex w-full items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2.5 text-[13px] font-medium text-ink transition-all hover:border-accent/40 hover:bg-accent-soft/60"
          >
            <Plus size={15} className="text-accent transition-transform group-hover:rotate-90" />
            <span className="flex-1 text-left">新对话</span>
            <span className="kbd">⌘K</span>
          </button>
        </div>

        <div className="px-4 pb-1.5 pt-4 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted">
          对话
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto px-2.5 pb-3 scroll-thin">
          {conversations.length === 0 && (
            <p className="px-2 py-6 text-center text-[12px] leading-relaxed text-muted">
              还没有对话
              <br />
              点上面的「新对话」开始
            </p>
          )}
          {conversations.map((conv) => {
            const active = conv.id === activeId;
            return (
              <button
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={cn(
                  'group flex w-full items-center gap-2.5 rounded-xl px-2.5 py-[7px] text-left transition-colors',
                  active ? 'bg-subtle text-ink' : 'text-muted hover:bg-subtle/60 hover:text-ink',
                )}
              >
                <MessageSquare
                  size={13.5}
                  className={cn('shrink-0', active ? 'text-accent' : 'opacity-55')}
                />
                <span className="flex-1 truncate text-[13px]">{conv.title}</span>
                <span
                  className={cn(
                    'shrink-0 text-[10px] tabular-nums',
                    active ? 'text-muted' : 'text-muted/60',
                  )}
                >
                  {conv.createdAt}
                </span>
              </button>
            );
          })}
        </div>

        <div className="space-y-0.5 border-t border-line px-2.5 py-2.5">
          <FooterRow
            icon={<BookOpen size={14.5} />}
            label="知识库"
            hint={kbChunks > 0 ? `${kbChunks}` : undefined}
            onClick={onOpenKB}
          />
          <FooterRow icon={<Users size={14.5} />} label="人物关系" onClick={onOpenChars} />
          <FooterRow
            icon={dark ? <Sun size={14.5} /> : <Moon size={14.5} />}
            label={dark ? '浅色模式' : '深色模式'}
            onClick={onToggleTheme}
          />
          <div className="flex items-center gap-1.5 px-2.5 pb-1 pt-2 text-[10px] text-muted/70">
            <Sparkles size={11} className="text-accent/70" />
            <span>LangChain · LangGraph</span>
          </div>
        </div>
      </aside>
    </>
  );
}

function FooterRow({
  icon,
  label,
  hint,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-[7px] text-[13px] text-muted transition-colors hover:bg-subtle hover:text-ink"
    >
      <span className="text-muted/80">{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {hint && <span className="chip tabular-nums">{hint}</span>}
    </button>
  );
}
