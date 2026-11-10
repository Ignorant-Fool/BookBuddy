import { motion } from 'framer-motion';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Eye,
  FileText,
  Loader2,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import { useCallback, useRef, useState } from 'react';
import type { KBStats } from '../types';
import {
  clearKnowledgeBase,
  deleteSource,
  previewSource,
  uploadDocument,
} from '../lib/api';
import { errorMessage } from '../lib/format';
import { cn } from '../lib/cn';
import { toast } from '../lib/toast';
import { Modal, Sheet } from './ui/Overlay';

const ACCEPT = '.txt,.md,.docx,.doc,.pptx,.ppt,.pdf';
const PREVIEW_LIMIT = 20000;

interface Props {
  open: boolean;
  onClose: () => void;
  stats: KBStats | null;
  onRefresh: () => void;
}

export function KnowledgePanel({ open, onClose, stats, onRefresh }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [preview, setPreview] = useState<{ name: string; content: string } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      if (!list.length) return;
      for (const file of list) {
        setUploading(file.name);
        try {
          const result = await uploadDocument(file);
          if (result.error) {
            toast.error(`${file.name}：${result.error}`);
          } else {
            toast.success(
              `${file.name} 已入库 · ${result.chunks ?? 0} 个片段${
                result.chars ? ` · ${result.chars} 字` : ''
              }`,
            );
          }
        } catch (err) {
          toast.error(`${file.name} 上传失败：${errorMessage(err)}`);
        } finally {
          setUploading(null);
          onRefresh();
        }
      }
    },
    [onRefresh],
  );

  const openPreview = async (source: string) => {
    setPreviewLoading(true);
    setPreview({ name: source, content: '' });
    try {
      const content = await previewSource(source);
      setPreview({ name: source, content });
    } catch (err) {
      toast.error(`预览失败：${errorMessage(err)}`);
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const remove = async (source: string) => {
    try {
      await deleteSource(source);
      toast.success(`已删除 ${source}`);
      setPendingDelete(null);
      onRefresh();
    } catch (err) {
      toast.error(`删除失败：${errorMessage(err)}`);
    }
  };

  const clearAll = async () => {
    setClearing(true);
    try {
      await clearKnowledgeBase();
      toast.success('知识库已清空');
      onRefresh();
    } catch (err) {
      toast.error(`清空失败：${errorMessage(err)}`);
    } finally {
      setClearing(false);
    }
  };

  const sources = stats?.sources ?? [];
  const previewShown = preview?.content.slice(0, PREVIEW_LIMIT) ?? '';

  return (
    <>
      <Sheet
        open={open}
        onClose={onClose}
        title="知识库"
        subtitle={
          stats
            ? `${stats.source_count} 个文件 · ${stats.total_chunks} 个片段`
            : '正在读取…'
        }
        icon={
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent-soft text-accent">
            <BookOpen size={16} />
          </div>
        }
        footer={
          sources.length > 0 ? (
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] text-muted">
                支持 txt / md / docx / pptx / pdf，单文件 ≤ 50MB
              </p>
              <button
                onClick={() => void clearAll()}
                disabled={clearing}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] text-[rgb(var(--c-danger))] transition-colors hover:bg-[rgb(var(--c-danger))]/10 disabled:opacity-50"
              >
                {clearing ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                清空
              </button>
            </div>
          ) : undefined
        }
      >
        <div className="space-y-4 p-4">
          {/* 上传区 */}
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              void handleFiles(event.dataTransfer.files);
            }}
            onClick={() => inputRef.current?.click()}
            className={cn(
              'group cursor-pointer rounded-2xl border border-dashed p-5 text-center transition-all',
              dragging
                ? 'border-accent bg-accent-soft'
                : 'border-line bg-subtle/40 hover:border-accent/40 hover:bg-accent-soft/40',
            )}
          >
            <div className="mx-auto mb-2 grid h-10 w-10 place-items-center rounded-xl bg-surface text-accent shadow-sm">
              {uploading ? (
                <Loader2 size={17} className="animate-spin" />
              ) : (
                <UploadCloud size={17} />
              )}
            </div>
            <p className="text-[13px] font-medium text-ink">
              {uploading ? `正在处理 ${uploading}…` : '拖拽文件到这里，或点击选择'}
            </p>
            <p className="mt-1 text-[11px] text-muted">
              自动完成解析 → 语义切片 → 向量化 → 建索引
            </p>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              multiple
              className="hidden"
              onChange={(event) => {
                if (event.target.files) void handleFiles(event.target.files);
                event.target.value = '';
              }}
            />
          </div>

          {/* 文件列表 */}
          {sources.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-line/60 py-8 text-center">
              <FileText size={20} className="text-muted/50" />
              <p className="text-[12px] text-muted">知识库还是空的</p>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="flex items-center justify-between px-1 pb-1">
                <span className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted">
                  已收录
                </span>
                <span className="text-[10.5px] text-muted">点击预览</span>
              </div>
              {sources.map((source) => {
                const confirming = pendingDelete === source;
                return (
                  <motion.div
                    key={source}
                    layout
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="group flex items-center gap-2 rounded-xl border border-transparent px-2 py-2 transition-colors hover:border-line hover:bg-subtle/50"
                  >
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
                      <FileText size={13} />
                    </span>
                    <button
                      onClick={() => void openPreview(source)}
                      className="min-w-0 flex-1 truncate text-left text-[12.5px] text-ink/90 hover:text-accent"
                      title={source}
                    >
                      {source}
                    </button>
                    <button
                      onClick={() => void openPreview(source)}
                      className="rounded-md p-1.5 text-muted/70 opacity-70 transition-all hover:bg-surface hover:text-ink group-hover:opacity-100"
                      title="预览片段"
                    >
                      <Eye size={12.5} />
                    </button>
                    {confirming ? (
                      <button
                        onClick={() => void remove(source)}
                        onBlur={() => setPendingDelete(null)}
                        className="rounded-md bg-[rgb(var(--c-danger))] px-1.5 py-1 text-[10.5px] font-medium text-white"
                      >
                        确认删除
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setPendingDelete(source);
                          window.setTimeout(
                            () => setPendingDelete((cur) => (cur === source ? null : cur)),
                            3000,
                          );
                        }}
                        className="rounded-md p-1.5 text-muted/70 opacity-70 transition-all hover:bg-surface hover:text-[rgb(var(--c-danger))] group-hover:opacity-100"
                        title="删除"
                      >
                        <Trash2 size={12.5} />
                      </button>
                    )}
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </Sheet>

      <Modal
        open={Boolean(preview)}
        onClose={() => setPreview(null)}
        title={preview?.name ?? ''}
        subtitle={
          preview
            ? `共 ${preview.content.length} 字符${
                preview.content.length > PREVIEW_LIMIT ? ` · 仅显示前 ${PREVIEW_LIMIT} 字符` : ''
              }`
            : ''
        }
        icon={
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-subtle text-muted">
            <FileText size={16} />
          </div>
        }
        width="max-w-[760px]"
      >
        <div className="p-4">
          {previewLoading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-[12.5px] text-muted">
              <Loader2 size={15} className="animate-spin" />
              正在读取片段…
            </div>
          ) : (
            <pre className="max-h-[62vh] overflow-y-auto whitespace-pre-wrap break-words rounded-xl border border-line bg-subtle/40 p-4 font-sans text-[12.5px] leading-[1.85] text-ink/90 scroll-thin">
              {previewShown || '（无内容）'}
            </pre>
          )}
        </div>
      </Modal>
    </>
  );
}

/* 供空状态复用的小图标 */
export const KBHint = ({ ok }: { ok: boolean }) =>
  ok ? (
    <CheckCircle2 size={14} className="text-accent" />
  ) : (
    <AlertCircle size={14} className="text-muted" />
  );
