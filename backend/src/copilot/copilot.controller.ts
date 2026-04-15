import {
  All,
  Controller,
  Req,
  Res,
  Next,
  OnModuleInit,
} from '@nestjs/common';
import type { Request, Response, NextFunction, RequestHandler } from 'express';
import { CopilotRuntime } from '@copilotkit/runtime/v2';
import { createCopilotExpressHandler } from '@copilotkit/runtime/v2/express';
import { HttpAgent } from '@copilotkit/runtime/v2';

/**
 * CopilotController
 *
 * Mounts the CopilotKit Runtime as an Express router inside NestJS.
 * The runtime proxies requests to the Python LangGraph agent via HttpAgent.
 *
 * All routes under /copilotkit/** are handled here.
 */
@Controller('copilotkit')
export class CopilotController implements OnModuleInit {
  private handler!: RequestHandler;

  onModuleInit(): void {
    const agentUrl = process.env.AGENT_URL ?? 'http://localhost:8000/copilotkit';

    const runtime = new CopilotRuntime({
      agents: {
        default: new HttpAgent({ url: agentUrl }),
      },
    });

    this.handler = createCopilotExpressHandler({
      runtime,
      basePath: '/copilotkit',
      cors: false,
    }) as unknown as RequestHandler;
  }

  @All('*')
  handle(
    @Req() req: Request,
    @Res() res: Response,
    @Next() next: NextFunction,
  ): void {
    this.handler(req, res, next);
  }
}
