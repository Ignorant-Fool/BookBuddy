import { useCallback, useEffect, useState } from 'react';
import { MotionConfig } from 'framer-motion';
import type { Conversation, HistoryItem, KBStats } from './types';
import { fetchStats } from './lib/api';
import { NavSidebar } from './components/NavSidebar';
import { KnowledgePanel } from './components/KnowledgePanel';
import { CharactersPanel } from './components/CharactersPanel';
import { Toaster } from './components/ui/Toaster';
import { ChatPage } from './pages/ChatPage';

const THEME_KEY = 'bookbuddy:theme';
const STORE_KEY = 'bookbuddy:conversations';

const uid = (prefix: string) =>
  `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

function readTheme(): boolean {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'dark') return true;
  if (saved === 'light') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function readConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function newConversation(): Conversation {
  return {
    id: uid('conv'),
    title: '新对话',
    messages: [],
    sessionId: uid('sess'),
    createdAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  };
}

export default function AppShell() {
  const [dark, setDark] = useState(readTheme);
  const [conversations, setConversations] = useState<Conversation[]>(readConversations);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [kbOpen, setKbOpen] = useState(false);
  const [charsOpen, setCharsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [stats, setStats] = useState<KBStats | null>(null);

  /* ---------------- 主题 ---------------- */
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light');
  }, [dark]);

  /* ---------------- 持久化 ---------------- */
  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(conversations));
    } catch {
      /* 配额溢出时忽略 */
    }
  }, [conversations]);

  /* ---------------- 知识库统计 ---------------- */
  const refreshStats = useCallback(async () => {
    try {
      setStats(await fetchStats());
    } catch {
      /* 后端未启动时静默失败 */
    }
  }, []);

  useEffect(() => {
    void refreshStats();
  }, [refreshStats]);

  /* ---------------- 对话操作 ---------------- */
  const create = useCallback((): Conversation => {
    const conv = newConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    setSidebarOpen(false);
    return conv;
  }, []);

  const updateMessages = useCallback((convId: string, messages: HistoryItem[]) => {
    setConversations((prev) =>
      prev.map((conv) => {
        if (conv.id !== convId) return conv;
        const first = messages.find((m) => m.question && !m.question.startsWith('(未识别'));
        const title = first ? first.question.slice(0, 22) : conv.title;
        return { ...conv, messages, title };
      }),
    );
  }, []);

  /* ---------------- 快捷键 ---------------- */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        create();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [create]);

  const active = conversations.find((conv) => conv.id === activeId) ?? null;

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex h-screen w-full overflow-hidden bg-canvas text-ink">
      <NavSidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={(id) => {
          setActiveId(id);
          setSidebarOpen(false);
        }}
        onNew={() => {
          create();
        }}
        onOpenKB={() => setKbOpen(true)}
        onOpenChars={() => setCharsOpen(true)}
        dark={dark}
        onToggleTheme={() => setDark((v) => !v)}
        kbChunks={stats?.total_chunks ?? 0}
        mobileOpen={sidebarOpen}
        onCloseMobile={() => setSidebarOpen(false)}
      />

      <main className="relative flex min-w-0 flex-1 flex-col bg-canvas">
        <ChatPage
          conversation={active}
          onCreateConversation={create}
          onUpdateMessages={updateMessages}
          kbChunks={stats?.total_chunks ?? 0}
          kbFiles={stats?.source_count ?? 0}
          onOpenSidebar={() => setSidebarOpen(true)}
          onOpenKB={() => setKbOpen(true)}
        />
      </main>

      <KnowledgePanel
        open={kbOpen}
        onClose={() => setKbOpen(false)}
        stats={stats}
        onRefresh={() => void refreshStats()}
      />
      <CharactersPanel
        open={charsOpen}
        onClose={() => setCharsOpen(false)}
        kbReady={(stats?.total_chunks ?? 0) > 0}
      />
      <Toaster />
      </div>
    </MotionConfig>
  );
}
