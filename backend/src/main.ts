import { NestFactory } from '@nestjs/core';
import type { NestExpressApplication } from '@nestjs/platform-express';
import { json, urlencoded } from 'express';
import { AppModule } from './app.module';

async function bootstrap() {
  // Global process-level safety nets.
  //
  // The CopilotKit runtime proxies SSE from the upstream LangGraph agent via
  // undici. If the upstream closes the connection with a malformed last chunk
  // (HPE_INVALID_CHUNK_SIZE) or the stream is aborted mid-flight, undici emits
  // an async error that is NOT attached to the original request promise chain
  // — Node treats it as an unhandledRejection and terminates the whole
  // NestJS process. That is what's causing the container to restart every
  // time the agent streams a tool call. We swallow those specific errors
  // here so one bad stream does not take the whole backend down.
  process.on('unhandledRejection', (reason: unknown) => {
    const err = reason as { code?: string; name?: string; message?: string; cause?: { code?: string } } | null;
    const code = err?.code ?? err?.cause?.code;
    const msg = err?.message ?? String(reason);
    if (
      code === 'HPE_INVALID_CHUNK_SIZE' ||
      code === 'UND_ERR_SOCKET' ||
      code === 'UND_ERR_ABORTED' ||
      msg === 'terminated' ||
      msg === 'Thread already running'
    ) {
      console.warn('[backend] swallowed recoverable stream error:', code ?? err?.name, msg);
      return;
    }
    console.error('[backend] unhandledRejection:', reason);
  });

  process.on('uncaughtException', (err: Error & { code?: string; cause?: { code?: string } }) => {
    const code = err.code ?? err.cause?.code;
    if (
      code === 'HPE_INVALID_CHUNK_SIZE' ||
      code === 'UND_ERR_SOCKET' ||
      code === 'UND_ERR_ABORTED' ||
      err.message === 'terminated'
    ) {
      console.warn('[backend] swallowed uncaughtException from upstream stream:', code ?? err.name, err.message);
      return;
    }
    console.error('[backend] uncaughtException:', err);
  });

  const app = await NestFactory.create<NestExpressApplication>(AppModule, { rawBody: true });

  // Raise body-parser limits — CopilotKit requests can be several hundred KB
  // once readables and tool results accumulate.
  app.use(json({ limit: '10mb' }));
  app.use(urlencoded({ extended: true, limit: '10mb' }));

  const origins = (process.env.CORS_ORIGINS ?? '*')
    .split(',')
    .map((s) => s.trim());

  app.enableCors({
    origin: origins.includes('*') ? true : origins,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'x-copilotkit-runtime-client-gql-version',
    ],
    credentials: false,
  });

  const port = parseInt(process.env.PORT ?? '3001', 10);
  await app.listen(port, '0.0.0.0');
  console.log(`NestJS backend listening on http://0.0.0.0:${port}`);
}

bootstrap();
