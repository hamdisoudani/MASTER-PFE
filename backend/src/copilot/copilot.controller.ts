import { All, Controller, Req, Res } from '@nestjs/common';
import { Request, Response } from 'express';
import {
  CopilotRuntime,
  OpenAIAdapter,
  copilotRuntimeNestEndpoint,
} from '@copilotkit/runtime';
import { AgentService } from '../agent/agent.service';

@Controller('copilot')
export class CopilotController {
  constructor(private readonly agentService: AgentService) {}

  @All()
  async handleCopilot(@Req() req: Request, @Res() res: Response) {
    const graph = await this.agentService.getGraph();
    const serviceAdapter = new OpenAIAdapter({
      openai: { apiKey: process.env.OPENAI_API_KEY } as any,
    });
    const runtime = new CopilotRuntime({
      agents: {
        myAgent: {
          graph,
          description: 'A helpful planning assistant',
        },
      } as any,
    });
    const handler = copilotRuntimeNestEndpoint({
      runtime,
      serviceAdapter,
      endpoint: '/copilot',
    });
    return handler(req, res);
  }
}
