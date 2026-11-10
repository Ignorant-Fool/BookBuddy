import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUp, Loader2, Mic, Paperclip, Square, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { startWavRecording, type WavRecording } from '../lib/recorder';
import { cn } from '../lib/cn';
import { toast } from '../lib/toast';

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  onAudio: (blob: Blob) => void;
  loading: boolean;
}

const MAX_CHARS = 4000;

export function ComposerBar({ value, onChange, onSend, onAudio, loading }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const recorderRef = useRef<WavRecording | null>(null);
  const [recording, setRecording] = useState(false);
  const [starting, setStarting] = useState(false);
  const [seconds, setSeconds] = useState(0);

  const autoSize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => {
    autoSize();
  }, [value, autoSize]);

  useEffect(() => {
    if (!recording) return;
    setSeconds(0);
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  const submit = () => {
    const text = value.trim();
    if (!text || loading) return;
    onSend(text);
    onChange('');
  };

  /* ---------------- 录音 ---------------- */
  const begin = useCallback(async (): Promise<boolean> => {
    if (recorderRef.current || starting || loading) return false;
    setStarting(true);
    try {
      recorderRef.current = await startWavRecording();
      setRecording(true);
      return true;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '无法访问麦克风');
      return false;
    } finally {
      setStarting(false);
    }
  }, [loading, starting]);

  const finish = useCallback(async () => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    setRecording(false);
    if (!recorder) return;
    try {
      const blob = await recorder.stop();
      if (blob.size < 2400) {
        toast.warning('录音太短了，请说完再松开');
        return;
      }
      onAudio(blob);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '录音失败');
    }
  }, [onAudio]);

  const cancel = useCallback(() => {
    recorderRef.current?.cancel();
    recorderRef.current = null;
    setRecording(false);
  }, []);

  /* ---------------- 空格键按住说话 ---------------- */
  useEffect(() => {
    const isTyping = () => {
      const tag = (document.activeElement?.tagName || '').toLowerCase();
      return tag === 'input' || tag === 'textarea';
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && recorderRef.current) {
        event.preventDefault();
        cancel();
        return;
      }
      if (event.key !== ' ' || event.repeat) return;
      if (isTyping() || loading || recorderRef.current) return;
      event.preventDefault();
      void begin();
    };

    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key !== ' ' || !recorderRef.current) return;
      event.preventDefault();
      void finish();
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [begin, cancel, finish, loading]);

  const mmss = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  const canSend = Boolean(value.trim()) && !loading && !recording;

  return (
    <div className="shrink-0 bg-canvas/85 px-3 pb-3.5 pt-1.5 backdrop-blur-xl sm:px-5">
      <div className="mx-auto w-full max-w-[760px]">
        <AnimatePresence>
          {recording && (
            <motion.div
              initial={{ opacity: 0, y: 6, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: 6, height: 0 }}
              className="overflow-hidden"
            >
              <div className="mb-2 flex items-center gap-2.5 rounded-xl border border-[rgb(var(--c-danger))]/25 bg-[rgb(var(--c-danger))]/[0.06] px-3 py-2">
                <span className="relative flex h-2.5 w-2.5 items-center justify-center">
                  <span className="absolute h-2.5 w-2.5 animate-ping rounded-full bg-[rgb(var(--c-danger))]/40" />
                  <span className="h-2 w-2 rounded-full bg-[rgb(var(--c-danger))]" />
                </span>
                <span className="font-mono text-[12px] tabular-nums text-[rgb(var(--c-danger))]">
                  {mmss}
                </span>
                <span className="flex-1 text-[11.5px] text-muted">
                  正在录音，说完松开空格或点停止
                </span>
                <button
                  onClick={cancel}
                  className="rounded-lg p-1 text-muted transition-colors hover:bg-subtle hover:text-ink"
                  title="取消（Esc）"
                >
                  <X size={13} />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div
          className={cn(
            'flex items-end gap-1 rounded-2xl border bg-surface px-1.5 py-1.5 shadow-soft transition-all duration-200',
            recording
              ? 'border-[rgb(var(--c-danger))]/45 ring-4 ring-[rgb(var(--c-danger))]/[0.07]'
              : 'border-line focus-within:border-accent/40 focus-within:ring-4 focus-within:ring-accent/[0.06]',
          )}
        >
          <button
            onClick={() => fileRef.current?.click()}
            disabled={loading || recording}
            className="mb-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl text-muted transition-colors hover:bg-subtle hover:text-ink disabled:opacity-35"
            title="上传音频"
          >
            <Paperclip size={16} />
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="audio/*,.mp3,.wav,.m4a,.webm,.ogg,.flac"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onAudio(file);
              event.target.value = '';
            }}
          />

          <textarea
            ref={textareaRef}
            value={value}
            rows={1}
            maxLength={MAX_CHARS}
            disabled={loading || recording}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            placeholder={
              recording ? '录音中…' : loading ? '正在回答…' : '问点什么，或按住空格说一句话'
            }
            className="max-h-[160px] min-h-[32px] flex-1 resize-none bg-transparent px-1 py-[7px] text-[14px] leading-[1.6] text-ink outline-none placeholder:text-muted/60 disabled:opacity-60"
          />

          <div className="mb-0.5 flex shrink-0 items-center gap-0.5">
            <button
              onClick={() => (recording ? void finish() : void begin())}
              disabled={loading || starting}
              className={cn(
                'grid h-8 w-8 place-items-center rounded-xl transition-all duration-200 disabled:opacity-35',
                recording
                  ? 'bg-[rgb(var(--c-danger))] text-white shadow-sm'
                  : 'text-muted hover:bg-subtle hover:text-ink',
              )}
              title={recording ? '结束录音' : '按住空格录音'}
            >
              {starting ? (
                <Loader2 size={15} className="animate-spin" />
              ) : recording ? (
                <Square size={13} className="fill-current" />
              ) : (
                <Mic size={16} />
              )}
            </button>

            <button
              onClick={submit}
              disabled={!canSend}
              className={cn(
                'grid h-8 w-8 place-items-center rounded-xl transition-all duration-200',
                canSend
                  ? 'bg-accent text-accent-fg shadow-sm hover:brightness-105 active:scale-95'
                  : 'bg-subtle text-muted/50',
              )}
              title="发送（Enter）"
            >
              {loading ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={16} />}
            </button>
          </div>
        </div>

        <div className="mt-1.5 flex items-center justify-center gap-3 text-[10.5px] text-muted/60">
          <span className="hidden sm:inline">
            <span className="kbd font-sans">Enter</span> 发送
          </span>
          <span className="hidden sm:inline">·</span>
          <span className="hidden sm:inline">
            <span className="kbd font-sans">Shift + Enter</span> 换行
          </span>
          <span className="hidden sm:inline">·</span>
          <span>按住空格录音</span>
        </div>
      </div>
    </div>
  );
}
