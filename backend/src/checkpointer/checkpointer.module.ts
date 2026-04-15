import { Module } from '@nestjs/common';
import { CheckpointerService } from './checkpointer.service';

@Module({
  providers: [CheckpointerService],
  exports: [CheckpointerService],
})
export class CheckpointerModule {}
