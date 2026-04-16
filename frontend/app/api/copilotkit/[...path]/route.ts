/**
 * Next.js catch-all proxy route for CopilotKit.
 *
 * Why this exists:
 *   The frontend's <CopilotKit runtimeUrl="/api/copilotkit"> sends
 *   requests to the Next.js origin. This route forwards them to the
 *   NestJS backend (BACKEND_URL) so the browser never needs to know
 *   the backend's public URL, and CORS is avoided entirely.
 *
 * Required Railway env var on the FRONTEND service:
 *   BACKEND_URL=https://backend-production-47f8.up.railway.app
 */
import { NextRequest } from 'next/server';

const BACKEND = (process.env.BACKEND_URL ?? 'http://localhost:3001').replace(/\/$/, '');

type Params = Promise<{ path?: string[] }>;

async function proxy(req: NextRequest, params: Params): Promise<Response> {
  const { path = [] } = await params;
  const subPath = path.length ? `/${path.join('/')}` : '';
  const target = `${BACKEND}/copilotkit${subPath}`;

  const headers = new Headers(req.headers);
  headers.delete('host');

  let body: ArrayBuffer | null = null;
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: body ?? undefined,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: upstream.headers,
  });
}

export async function GET(req: NextRequest, { params }: { params: Params }) {
  return proxy(req, params);
}

export async function POST(req: NextRequest, { params }: { params: Params }) {
  return proxy(req, params);
}

export async function OPTIONS() {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers':
        'Content-Type, Authorization, x-copilotkit-runtime-client-gql-version',
    },
  });
}
