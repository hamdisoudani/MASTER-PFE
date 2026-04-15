import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ChatsModule } from './chats/chats.module';
import { CopilotModule } from './copilot/copilot.module';
import { ChatEntity } from './chats/chat.entity';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),

    TypeOrmModule.forRoot({
      type: 'better-sqlite3',
      database: process.env.DB_PATH ?? './data/chats.sqlite',
      entities: [ChatEntity],
      synchronize: true,
    }),

    ChatsModule,
    CopilotModule,
  ],
})
export class AppModule {}
