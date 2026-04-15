import { Body, Controller, Delete, Get, Param, Patch, Post, Query } from '@nestjs/common';
import { ChatsService } from './chats.service';

@Controller('chats')
export class ChatsController {
  constructor(private readonly chatsService: ChatsService) {}

  @Post()
  create(@Body() body: { userId: string; title?: string }) {
    return this.chatsService.create(body.userId, body.title);
  }

  @Get()
  findAll(@Query('userId') userId?: string) { return this.chatsService.findAll(userId); }

  @Get(':id')
  findOne(@Param('id') id: string) { return this.chatsService.findOne(id); }

  @Patch(':id')
  update(@Param('id') id: string, @Body() body: { title: string }) {
    return this.chatsService.update(id, body.title);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    this.chatsService.remove(id);
    return { success: true };
  }
}
