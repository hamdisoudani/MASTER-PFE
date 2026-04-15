import { Module } from '@nestjs/common';
import { CopilotModule } from './copilot/copilot.module';
import { HealthController } from './health.controller';

@Module({
  imports: [CopilotModule],
  controllers: [HealthController],
})
export class AppModule {}
