import { Injectable } from '@nestjs/common';
import { v4 as uuidv4 } from 'uuid';
import { Chat } from './chat.entity';

@Injectable()
export class ChatsService {
  private chats: Map<string, Chat> = new Map();

  create(userId: string, title?: string): Chat {
    const id = uuidv4();
    const threadId = uuidv4();
    const now = new Date().toISOString();
    const chat: Chat = { id, userId, threadId, title: title ?? 'New Chat', createdAt: now, updatedAt: now };
    this.chats.set(id, chat);
    return chat;
  }

  findAll(userId?: string): Chat[] {
    const all = Array.from(this.chats.values());
    return userId ? all.filter((c) => c.userId === userId) : all;
  }

  findOne(id: string): Chat | undefined { return this.chats.get(id); }

  update(id: string, title: string): Chat | undefined {
    const chat = this.chats.get(id);
    if (!chat) return undefined;
    chat.title = title;
    chat.updatedAt = new Date().toISOString();
    return chat;
  }

  remove(id: string): boolean { return this.chats.delete(id); }
}
