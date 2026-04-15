export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
}

export interface Chat {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateChatPayload { title: string; }

export interface AddMessagePayload {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
}

export interface AgentState {
  plan: string[] | null;
  mode: 'chat' | 'research' | 'plan';
  finished: boolean;
}
