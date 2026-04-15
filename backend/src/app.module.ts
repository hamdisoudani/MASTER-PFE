import { Module } from '@nestjs/common';
import { ServeStaticModule } from '@nestjs/serve-static';
import { join } from 'path';
import { AgentModule } from './agent/agent.module';
import { CheckpointerModule } from './checkpointer/checkpointer.module';
import { CopilotModule } from './copilot/copilot.module';
import { ChatsModule } from './chats/chats.module';

@Module({
  imports: [
    ServeStaticModule.forRoot({
      rootPath: join(__dirname, '..', 'public'),
      serveRoot: '/',
    }),
    CheckpointerModule,
    AgentModule,
    CopilotModule,
    ChatsModule,
  ],
})
export class AppModule {}
