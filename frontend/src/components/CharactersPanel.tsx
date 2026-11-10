import { motion } from 'framer-motion';
import { Loader2, Search, Sparkles, UserRound, Users } from 'lucide-react';
import { useState } from 'react';
import type { Character } from '../types';
import { extractCharacters } from '../lib/api';
import { errorMessage } from '../lib/format';
import { cn } from '../lib/cn';
import { toast } from '../lib/toast';
import { Modal } from './ui/Overlay';

interface Props {
  open: boolean;
  onClose: () => void;
  kbReady: boolean;
}

export function CharactersPanel({ open, onClose, kbReady }: Props) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const run = async (text: string) => {
    if (!kbReady) {
      toast.warning('知识库为空，请先上传书籍');
      return;
    }
    setLoading(true);
    try {
      const list = await extractCharacters(text.trim());
      setCharacters(list);
      setSelected(list[0]?.name ?? null);
      if (!list.length) toast.info('没有提取到人物信息');
      else toast.success(`已梳理 ${list.length} 个人物`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const current = characters?.find((c) => c.name === selected) ?? null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="人物关系"
      subtitle={
        characters ? `${characters.length} 个人物` : '输入人物名查询，或提取全书主要人物'
      }
      icon={
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent-soft text-accent">
          <Users size={16} />
        </div>
      }
      width="max-w-[900px]"
    >
      <div className="flex h-[540px] flex-col sm:flex-row">
        {/* 左：搜索 + 列表 */}
        <div className="flex min-h-0 w-full flex-col border-b border-line sm:w-[300px] sm:border-b-0 sm:border-r">
          <div className="space-y-2 border-b border-line/70 p-3">
            <div className="flex items-center gap-1.5 rounded-xl border border-line bg-canvas px-2.5 py-1.5 transition-colors focus-within:border-accent/40">
              <Search size={13} className="shrink-0 text-muted" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && query.trim()) void run(query);
                }}
                placeholder="人物名，如 林黛玉"
                className="min-w-0 flex-1 bg-transparent text-[12.5px] text-ink outline-none placeholder:text-muted/60"
              />
            </div>
            <div className="flex gap-1.5">
              <button
                onClick={() => void run(query)}
                disabled={loading || !query.trim()}
                className="btn btn-primary h-8 flex-1 text-[12px]"
              >
                {loading ? <Loader2 size={13} className="animate-spin" /> : null}
                查询
              </button>
              <button
                onClick={() => void run('')}
                disabled={loading}
                className="btn btn-outline h-8 flex-1 text-[12px]"
              >
                全部提取
              </button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-2 scroll-thin">
            {!characters && !loading && (
              <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
                <UserRound size={20} className="text-muted/40" />
                <p className="text-[11.5px] leading-relaxed text-muted">
                  输入一个人物名，
                  <br />
                  或直接「全部提取」
                </p>
              </div>
            )}
            {loading && (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-muted">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-[11.5px]">大模型正在梳理…</span>
              </div>
            )}
            {characters?.map((char) => {
              const active = char.name === selected;
              return (
                <button
                  key={char.name}
                  onClick={() => setSelected(char.name)}
                  className={cn(
                    'mb-0.5 flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-colors',
                    active ? 'bg-accent-soft text-accent' : 'text-ink/85 hover:bg-subtle',
                  )}
                >
                  <span
                    className={cn(
                      'grid h-6 w-6 shrink-0 place-items-center rounded-md text-[10px] font-semibold',
                      active ? 'bg-accent text-accent-fg' : 'bg-subtle text-muted',
                    )}
                  >
                    {char.name.slice(0, 1)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium">
                    {char.name}
                  </span>
                  {char.relations && (
                    <span className="shrink-0 text-[10px] tabular-nums text-muted">
                      {char.relations.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* 右：详情 */}
        <div className="min-h-0 flex-1 overflow-y-auto p-5 scroll-thin">
          {current ? (
            <motion.div
              key={current.name}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
            >
              <div className="flex items-center gap-3">
                <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-teal-500 to-emerald-700 text-[17px] font-semibold text-white shadow-sm">
                  {current.name.slice(0, 1)}
                </div>
                <div className="min-w-0">
                  <h3 className="truncate text-[18px] font-semibold tracking-tight text-ink">
                    {current.name}
                  </h3>
                  {current.relation && (
                    <p className="mt-0.5 text-[12px] text-accent">{current.relation}</p>
                  )}
                </div>
              </div>

              {current.description && (
                <p className="mt-4 rounded-xl border border-line bg-subtle/40 p-3.5 text-[13px] leading-relaxed text-ink/85">
                  {current.description}
                </p>
              )}

              {current.relations && current.relations.length > 0 && (
                <div className="mt-5">
                  <div className="mb-2 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted">
                    <Sparkles size={11} className="text-accent" />
                    关联人物
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {current.relations.map((rel, index) => (
                      <span
                        key={`${rel.with}-${index}`}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[12px]"
                      >
                        <span className="font-medium text-ink">{rel.with}</span>
                        <span className="h-3 w-px bg-line" />
                        <span className="text-muted">{rel.type}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <Users size={22} className="text-muted/40" />
              <p className="text-[12px] text-muted">选择左侧人物查看详情</p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
