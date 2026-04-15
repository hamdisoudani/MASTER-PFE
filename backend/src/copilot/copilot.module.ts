import { Module } from '@nestjs/common';
import { CopilotController } from './copilot.controller';
import { AgentModule } from '../agent/agent.module';

@Module({
  imports: [AgentModule],
  controllers: [CopilotController],
})
export class CopilotModule {}
