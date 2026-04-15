import { All, Controller, Req, Res } from '@nestjs/common';
import { CopilotRuntime, copilotRuntimeNestEndpoint } from '@copilotkit/runtime';
import { LangGraphHttpAgent } from '@copilotkit/runtime/langgraph';
import { Request, Response } from 'express';

@Controller('copilotkit')
export class CopilotController {
  @All('*path')
  async copilotEndpoint(@Req() req: Request, @Res() res: Response) {
    const agentUrl =
      process.env.AGENT_URL ?? 'http://localhost:8000/copilotkit';

    const runtime = new CopilotRuntime({
      agents: {
        default: new LangGraphHttpAgent({ url: agentUrl }),
      },
    });

    const handler = copilotRuntimeNestEndpoint({
      runtime,
      endpoint: '/copilotkit',
    });

    return handler(req, res);
  }
}
