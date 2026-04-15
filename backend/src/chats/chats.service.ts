import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ChatEntity, ChatMessage } from './chat.entity';
import { CreateChatDto } from './dto/create-chat.dto';
import { AddMessageDto } from './dto/add-message.dto';

@Injectable()
export class ChatsService {
  constructor(
    @InjectRepository(ChatEntity)
    private readonly repo: Repository<ChatEntity>,
  ) {}

  async findAll(): Promise<ChatEntity[]> {
    return this.repo.find({ order: { updatedAt: 'DESC' } });
  }

  async findOne(id: string): Promise<ChatEntity> {
    const chat = await this.repo.findOne({ where: { id } });
    if (!chat) throw new NotFoundException(`Chat ${id} not found`);
    return chat;
  }

  async create(dto: CreateChatDto): Promise<ChatEntity> {
    const chat = this.repo.create({ title: dto.title });
    chat.messages = [];
    return this.repo.save(chat);
  }

  async addMessage(id: string, dto: AddMessageDto): Promise<ChatEntity> {
    const chat = await this.findOne(id);
    const msg: ChatMessage = {
      id: dto.id,
      role: dto.role,
      content: dto.content,
      createdAt: dto.createdAt,
    };
    chat.messages = [...chat.messages, msg];
    return this.repo.save(chat);
  }

  async remove(id: string): Promise<void> {
    const chat = await this.findOne(id);
    await this.repo.remove(chat);
  }
}
