import { All, Controller, Req, Res } from '@nestjs/common';
import {
  CopilotRuntime,
  HttpAgent,
  copilotRuntimeNestEndpoint,
} from '@copilotkit/runtime';
import { Request, Response } from 'express';

@Controller('copilotkit')
export class CopilotController {
  @All('*')
  async copilotEndpoint(@Req() req: Request, @Res() res: Response) {
    const agentUrl = process.env.AGENT_URL ?? 'http://localhost:8000/copilotkit';

    const runtime = new CopilotRuntime({
      agents: {
        default: new HttpAgent({ url: agentUrl }),
      },
    });

    const handler = copilotRuntimeNestEndpoint({ runtime });
    return handler(req, res);
  }
}
