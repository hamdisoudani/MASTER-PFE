import { Module } from '@nestjs/common';
import { CopilotModule } from './copilot/copilot.module';

@Module({
  imports: [CopilotModule],
})
export class AppModule {}
