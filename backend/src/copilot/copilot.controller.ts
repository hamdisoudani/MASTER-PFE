import { All, Controller, Req, Res } from '@nestjs/common';
import { CopilotRuntime, copilotRuntimeNestEndpoint } from '@copilotkit/runtime';
import { LangGraphHttpAgent } from '@copilotkit/runtime/langgraph';
import { Request, Response } from 'express';

@Controller('copilotkit')
export class CopilotController {
  private getHandler() {
    const agentUrl =
      process.env.AGENT_URL ?? 'http://localhost:8000/copilotkit';

    const runtime = new CopilotRuntime({
      agents: {
        default: new LangGraphHttpAgent({ url: agentUrl }),
      },
    });

    return copilotRuntimeNestEndpoint({
      runtime,
      endpoint: '/copilotkit',
    });
  }

  @All()
  async copilotBase(@Req() req: Request, @Res() res: Response) {
    const handler = this.getHandler();
    return handler(req, res);
  }

  @All('*path')
  async copilotWildcard(@Req() req: Request, @Res() res: Response) {
    const handler = this.getHandler();
    return handler(req, res);
  }
}
