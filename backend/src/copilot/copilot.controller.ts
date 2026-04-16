import { All, Controller, Req, Res } from '@nestjs/common';
import { CopilotRuntime, copilotRuntimeNestEndpoint } from '@copilotkit/runtime';
import { LangGraphHttpAgent } from '@copilotkit/runtime/langgraph';
import { Request, Response } from 'express';

/**
 * Proxies all /copilotkit/* requests to the LangGraph FastAPI agent.
 *
 * Agent name 'syllabus_agent' must match:
 *   - agent/main.py      → LangGraphAGUIAgent(name='syllabus_agent')
 *   - frontend page.tsx  → <CopilotKit agent='syllabus_agent'>
 *
 * Required Railway env var on the BACKEND service:
 *   AGENT_URL=https://agent-production-43c3.up.railway.app/copilotkit
 */
@Controller('copilotkit')
export class CopilotController {
  private getHandler() {
    const agentUrl =
      process.env.AGENT_URL ?? 'http://localhost:8000/copilotkit';

    const runtime = new CopilotRuntime({
      agents: {
        syllabus_agent: new LangGraphHttpAgent({ url: agentUrl }),
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
