import { Module } from '@nestjs/common';
import { CopilotController } from './copilot.controller';

@Module({
  controllers: [CopilotController],
})
export class CopilotModule {}
