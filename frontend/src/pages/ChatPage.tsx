import { useCallback, useEffect, useRef, useState } from 'react';
import type { Conversation, HistoryItem } from '../types';
import { sendAudio, sendText } from '../lib/api';
import { clockNow, errorMessage } from '../lib/format';
import { toast } from '../lib/toast';
import { ChatHeader } from '../components/ChatHeader';
import { ComposerBar } from '../components/ComposerBar';
import { WelcomeHero } from '../components/WelcomeHero';
import { AssistantMessage, ThinkingBubble, UserMessage } from '../components/MessageBubble';

interface Props {
  conversation: Conversation | null;
  onCreateConversation: () => Conversation;
  onUpdateMessages: (convId: string, messages: HistoryItem[]) => void;
  kbChunks: number;
  kbFiles: number;
  onOpenSidebar: () => void;
  onOpenKB: () => void;
}

export function ChatPage({
  conversation,
  onCreateConversation,
  onUpdateMessages,
  kbChunks,
  kbFiles,
  onOpenSidebar,
  onOpenKB,
}: Props) {
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const activeRef = useRef<Conversation | null>(conversation);
  const busyRef = useRef(false);

  activeRef.current = conversation;

  const messages = conversation?.messages ?? [];
  const hasMessages = messages.length > 0;

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const frame = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, loading]);

  const ensureConversation = useCallback((): Conversation => {
    if (activeRef.current) return activeRef.current;
    const created = onCreateConversation();
    activeRef.current = created;
    return created;
  }, [onCreateConversation]);

  const append = useCallback(
    (conv: Conversation, item: HistoryItem) => {
      onUpdateMessages(conv.id, [...(conv.messages ?? []), item]);
    },
    [onUpdateMessages],
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (busyRef.current) return;
      busyRef.current = true;
      const conv = ensureConversation();
      setLoading(true);
      try {
        const data = await sendText(text, conv.sessionId);
        append(conv, {
          id: `${Date.now()}`,
          question: text,
          answer: data.llm_answer,
          confidence: 1,
          time: clockNow(),
          agent_steps: data.agent_steps,
          model: data.model,
          elapsed: data.elapsed,
        });
      } catch (err) {
        toast.error(`请求失败：${errorMessage(err)}`);
      } finally {
        setLoading(false);
        busyRef.current = false;
      }
    },
    [append, ensureConversation],
  );

  const handleAudio = useCallback(
    async (blob: Blob) => {
      if (busyRef.current) return;
      busyRef.current = true;
      const conv = ensureConversation();
      setLoading(true);
      try {
        const data = await sendAudio(blob, conv.sessionId);
        append(conv, {
          id: `${Date.now()}`,
          question: data.cleaned_text || data.asr_text || '(未识别)',
          answer: data.llm_answer,
          confidence: data.asr_confidence,
          time: clockNow(),
          duration: data.duration,
          waveform_image: data.waveform_image,
          mfcc_image: data.mfcc_image,
          mfcc_shape: data.mfcc_shape,
          agent_steps: data.agent_steps,
          model: data.model,
          elapsed: data.elapsed,
        });
        if (!data.cleaned_text) toast.warning('没有识别到有效语音');
      } catch (err) {
        toast.error(`语音处理失败：${errorMessage(err)}`);
      } finally {
        setLoading(false);
        busyRef.current = false;
      }
    },
    [append, ensureConversation],
  );

  const title = conversation?.title && conversation.title !== '新对话' ? conversation.title : '新对话';

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <ChatHeader
        title={title}
        kbChunks={kbChunks}
        kbFiles={kbFiles}
        onOpenSidebar={onOpenSidebar}
        onOpenKB={onOpenKB}
      />

      <div
        ref={scrollRef}
        className={`min-h-0 flex-1 overflow-y-auto scroll-thin ${
          hasMessages ? '' : 'flex flex-col'
        }`}
      >
        {hasMessages ? (
          <div className="mx-auto w-full max-w-[760px] space-y-7 px-4 py-6 sm:px-5">
            {messages.map((item) => (
              <div key={item.id}>
                <UserMessage item={item} />
                <div className="mt-3">
                  <AssistantMessage item={item} />
                </div>
              </div>
            ))}
            {loading && <ThinkingBubble />}
            <div className="h-2" />
          </div>
        ) : (
          <WelcomeHero hasKB={kbChunks > 0} onPick={setDraft} onOpenKB={onOpenKB} />
        )}
      </div>

      <ComposerBar
        value={draft}
        onChange={setDraft}
        onSend={(text) => void handleSend(text)}
        onAudio={(blob) => void handleAudio(blob)}
        loading={loading}
      />
    </div>
  );
}
