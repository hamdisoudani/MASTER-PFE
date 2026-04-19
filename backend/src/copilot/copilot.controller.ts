import { All, Controller, Req, Res, Logger } from '@nestjs/common';
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
 *
 * The runtime + handler are cached at module scope so we do not rebuild the
 * InMemoryAgentRunner on every request. Rebuilding per request was racy and
 * contributed to spurious "Thread already running" errors.
 */
let cachedHandler: ((req: Request, res: Response) => unknown) | null = null;

function getHandler(): (req: Request, res: Response) => unknown {
  if (cachedHandler) return cachedHandler;
  const agentUrl = process.env.AGENT_URL ?? 'http://localhost:8000/copilotkit';
  const runtime = new CopilotRuntime({
    agents: {
      syllabus_agent: new LangGraphHttpAgent({ url: agentUrl }),
    },
  });
  cachedHandler = copilotRuntimeNestEndpoint({
    runtime,
    endpoint: '/copilotkit',
  }) as unknown as (req: Request, res: Response) => unknown;
  return cachedHandler;
}

@Controller('copilotkit')
export class CopilotController {
  private readonly logger = new Logger(CopilotController.name);

  private async safeDispatch(req: Request, res: Response) {
    const handler = getHandler();
    try {
      await handler(req, res);
    } catch (err) {
      const e = err as { code?: string; message?: string; cause?: { code?: string } };
      const code = e?.code ?? e?.cause?.code;
      const msg = e?.message ?? String(err);

      // Known recoverable upstream-streaming failures. Log and respond, but
      // never rethrow — rethrowing propagates into undici and kills the
      // Node process via an unhandledRejection.
      if (
        code === 'HPE_INVALID_CHUNK_SIZE' ||
        code === 'UND_ERR_SOCKET' ||
        code === 'UND_ERR_ABORTED' ||
        msg === 'terminated'
      ) {
        this.logger.warn(`upstream stream aborted (${code ?? msg}) — responding 502`);
        if (!res.headersSent) {
          res.status(502).json({ error: 'upstream_stream_aborted', code, message: msg });
        } else {
          try { res.end(); } catch { /* already closed */ }
        }
        return;
      }

      if (msg === 'Thread already running') {
        this.logger.warn('thread already running — responding 409');
        if (!res.headersSent) {
          res.status(409).json({ error: 'thread_already_running' });
        } else {
          try { res.end(); } catch { /* already closed */ }
        }
        return;
      }

      this.logger.error('unexpected copilotkit error', err);
      if (!res.headersSent) {
        res.status(500).json({ error: 'internal_error', message: msg });
      } else {
        try { res.end(); } catch { /* already closed */ }
      }
    }
  }

  @All()
  async copilotBase(@Req() req: Request, @Res() res: Response) {
    return this.safeDispatch(req, res);
  }

  @All('*path')
  async copilotWildcard(@Req() req: Request, @Res() res: Response) {
    return this.safeDispatch(req, res);
  }
}
