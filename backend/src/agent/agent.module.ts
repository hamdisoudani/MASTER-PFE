import { Module } from '@nestjs/common';
import { AgentService } from './agent.service';
import { CheckpointerModule } from '../checkpointer/checkpointer.module';

@Module({
  imports: [CheckpointerModule],
  providers: [AgentService],
  exports: [AgentService],
})
export class AgentModule {}
