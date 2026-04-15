import { Injectable, OnModuleInit } from '@nestjs/common';
import { MemorySaver } from '@langchain/langgraph';

@Injectable()
export class CheckpointerService implements OnModuleInit {
  private checkpointer: MemorySaver;

  onModuleInit() {
    this.checkpointer = new MemorySaver();
    console.log('Checkpointer initialized (in-memory)');
  }

  async getCheckpointer(): Promise<MemorySaver> {
    return this.checkpointer;
  }
}
