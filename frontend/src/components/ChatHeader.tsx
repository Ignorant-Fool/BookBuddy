import { BookOpen, Menu, PanelLeft } from 'lucide-react';
import { cn } from '../lib/cn';

interface Props {
  title: string;
  kbChunks: number;
  kbFiles: number;
  onOpenSidebar: () => void;
  onOpenKB: () => void;
}

export function ChatHeader({ title, kbChunks, kbFiles, onOpenSidebar, onOpenKB }: Props) {
  const ready = kbChunks > 0;
  return (
    <header className="sticky top-0 z-20 flex h-[54px] shrink-0 items-center gap-2 border-b border-line/60 bg-canvas/80 px-3 backdrop-blur-xl sm:px-5">
      <button onClick={onOpenSidebar} className="icon-btn lg:hidden" aria-label="打开侧栏">
        <Menu size={18} />
      </button>

      <div className="flex min-w-0 flex-1 items-center gap-2">
        <PanelLeft size={14.5} className="hidden shrink-0 text-muted/60 lg:block" />
        <span className="truncate text-[13px] font-medium text-ink/90">{title}</span>
      </div>

      <button
        onClick={onOpenKB}
        className={cn(
          'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium transition-colors',
          ready
            ? 'border-accent/25 bg-accent-soft text-accent hover:border-accent/50'
            : 'border-line text-muted hover:border-muted/40 hover:text-ink',
        )}
        title="打开知识库"
      >
        <BookOpen size={12.5} />
        {ready ? (
          <span className="tabular-nums">
            {kbFiles} 个文件 · {kbChunks} 片段
          </span>
        ) : (
          <span>知识库为空</span>
        )}
        <span
          className={cn(
            'ml-0.5 h-1.5 w-1.5 rounded-full',
            ready ? 'bg-accent' : 'bg-muted/50',
          )}
        />
      </button>
    </header>
  );
}
