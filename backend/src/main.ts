import { NestFactory } from '@nestjs/core';
import type { NestExpressApplication } from '@nestjs/platform-express';
import { json, urlencoded } from 'express';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create<NestExpressApplication>(AppModule, { rawBody: true });

  // Raise body-parser limits — CopilotKit requests can be several hundred KB
  // once readables and tool results accumulate. Default 100kb was triggering
  // PayloadTooLargeError. Frontend already ships only a small skeleton, but
  // this is a safety net.
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
