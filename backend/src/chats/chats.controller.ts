import {
  Controller,
  Get,
  Post,
  Delete,
  Param,
  Body,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ChatsService } from './chats.service';
import { ChatEntity } from './chat.entity';
import { CreateChatDto } from './dto/create-chat.dto';
import { AddMessageDto } from './dto/add-message.dto';

@Controller('api/chats')
export class ChatsController {
  constructor(private readonly chatsService: ChatsService) {}

  @Get()
  findAll(): Promise<ChatEntity[]> {
    return this.chatsService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string): Promise<ChatEntity> {
    return this.chatsService.findOne(id);
  }

  @Post()
  create(@Body() dto: CreateChatDto): Promise<ChatEntity> {
    return this.chatsService.create(dto);
  }

  @Post(':id/messages')
  addMessage(
    @Param('id') id: string,
    @Body() dto: AddMessageDto,
  ): Promise<ChatEntity> {
    return this.chatsService.addMessage(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id') id: string): Promise<void> {
    return this.chatsService.remove(id);
  }
}
