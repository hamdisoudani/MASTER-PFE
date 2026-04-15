import type { Chat, CreateChatPayload, AddMessagePayload } from '@/types';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:3001';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' }, ...init,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const chatsApi = {
  list: (): Promise<Chat[]> => request<Chat[]>('/api/chats'),
  get: (id: string): Promise<Chat> => request<Chat>(`/api/chats/${id}`),
  create: (p: CreateChatPayload): Promise<Chat> => request<Chat>('/api/chats', { method: 'POST', body: JSON.stringify(p) }),
  addMessage: (id: string, p: AddMessagePayload): Promise<Chat> => request<Chat>(`/api/chats/${id}/messages`, { method: 'POST', body: JSON.stringify(p) }),
  delete: (id: string): Promise<void> => request<void>(`/api/chats/${id}`, { method: 'DELETE' }),
};
