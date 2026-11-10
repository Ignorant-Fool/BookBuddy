export interface AgentStep {
  type: string;
  content: string;
}

export interface HistoryItem {
  id: string;
  question: string;
  answer: string;
  confidence: number;
  time: string;
  duration?: number;
  waveform_image?: string;
  mfcc_image?: string;
  mfcc_shape?: [number, number];
  agent_steps?: AgentStep[];
  model?: string;
  elapsed?: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: HistoryItem[];
  sessionId: string;
  createdAt: string;
}

export interface KBStats {
  total_chunks: number;
  sources: string[];
  source_count: number;
}

export interface TextResult {
  success: true;
  cleaned_text: string;
  llm_answer: string;
  asr_confidence: number;
  agent_steps?: AgentStep[];
  model?: string;
  evidence_count?: number;
  elapsed?: number;
  refused?: boolean;
}

export interface AudioResult {
  success: true;
  duration: number;
  waveform_image: string;
  mfcc_image: string;
  mfcc_shape: [number, number];
  asr_text: string;
  asr_confidence: number;
  asr_model?: string;
  cleaned_text: string;
  llm_answer: string;
  agent_steps?: AgentStep[];
  model?: string;
  elapsed?: number;
}

export interface ErrorResult {
  success: false;
  error: string;
}

export interface Character {
  name: string;
  relation?: string;
  relations?: { with: string; type: string }[];
  description?: string;
}
