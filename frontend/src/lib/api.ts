import axios from 'axios';
import type { AudioResult, Character, KBStats, TextResult } from '../types';

export const http = axios.create({ timeout: 600000 });

export interface UploadedFile {
  file: string;
  chars?: number;
  chunks?: number;
  status?: string;
  error?: string;
}

/** 文本提问 */
export async function sendText(text: string, sessionId: string): Promise<TextResult> {
  const { data } = await http.post<TextResult>('/api/send-text', { text, session_id: sessionId });
  return data;
}

/** 语音提问 */
export async function sendAudio(blob: Blob, sessionId: string): Promise<AudioResult> {
  const form = new FormData();
  form.append('audio', blob, 'recording.wav');
  form.append('session_id', sessionId);
  const { data } = await http.post<AudioResult>('/api/process-audio', form);
  return data;
}

/** 知识库统计 */
export async function fetchStats(): Promise<KBStats> {
  const { data } = await http.get<{ success: boolean; stats: KBStats }>('/api/kb/stats');
  return data.stats;
}

/** 上传文档（后端支持多文件，这里逐个上传以便报错更清晰） */
export async function uploadDocument(file: File): Promise<UploadedFile> {
  const form = new FormData();
  form.append('file', file, file.name);
  const { data } = await http.post<{ success: boolean; results: UploadedFile[] }>(
    '/api/kb/upload',
    form,
  );
  return data.results?.[0] ?? { file: file.name, error: '服务端未返回结果' };
}

/** 预览文件的所有切片 */
export async function previewSource(source: string): Promise<string> {
  const { data } = await http.get<{ success: boolean; content: string }>('/api/kb/preview', {
    params: { source },
  });
  return data.content ?? '';
}

export async function deleteSource(source: string): Promise<void> {
  await http.delete('/api/kb/delete-source', { params: { source } });
}

export async function clearKnowledgeBase(): Promise<void> {
  await http.delete('/api/kb/clear');
}

/** 人物关系抽取 */
export async function extractCharacters(query: string): Promise<Character[]> {
  const { data } = await http.post<{
    success: boolean;
    data?: { characters: Character[] };
    error?: string;
  }>('/api/kb/characters', query ? { query } : {});
  if (!data.success) throw new Error(data.error || '抽取失败');
  return data.data?.characters ?? [];
}

export interface HealthInfo {
  status: string;
  knowledge_base: KBStats;
  sessions: number;
  models: Record<string, string>;
}

export async function fetchHealth(): Promise<HealthInfo> {
  const { data } = await http.get<HealthInfo>('/api/health');
  return data;
}
