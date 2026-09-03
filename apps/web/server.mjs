import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import { randomUUID } from 'node:crypto';

import { buildSecurityHeaders } from './security-headers.mjs';

const port = Number(process.env.PORT || 8080);
const staticRoot = resolve(process.env.STATIC_DIR || 'public');
const agentServiceUrl = process.env.AGENT_SERVICE_URL || '';
const maxRequestBodyBytes = 64 * 1024;
let cachedIdentityToken;

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

const securityHeaders = buildSecurityHeaders();

const server = createServer(async (request, response) => {
  const requestUrl = new URL(request.url || '/', `http://${request.headers.host || 'localhost'}`);

  try {
    if (requestUrl.pathname === '/api/chat') {
      await proxyChat(request, response);
      return;
    }

    if (requestUrl.pathname.startsWith('/api/')) {
      sendJson(response, 404, { detail: 'Endpoint non trovato.' });
      return;
    }

    await serveStaticFile(requestUrl.pathname, response);
  } catch (error) {
    console.error('web_request_failed', {
      message: error instanceof Error ? error.message : 'unknown error',
      path: requestUrl.pathname,
    });
    sendJson(response, 500, { detail: 'Errore interno del servizio web.' });
  }
});

server.listen(port, () => {
  console.log(`schema_assistant_web_listening port=${port}`);
});

async function proxyChat(request, response) {
  if (request.method !== 'POST') {
    sendJson(response, 405, { detail: 'Metodo non consentito.' });
    return;
  }

  let payload;
  try {
    payload = await readJsonBody(request);
  } catch (error) {
    const statusCode = error instanceof RequestBodyError ? error.statusCode : 400;
    sendJson(response, statusCode, { detail: error instanceof Error ? error.message : 'Payload non valido.' });
    return;
  }
  if (!isValidChatPayload(payload)) {
    sendJson(response, 400, { detail: 'Payload non valido.' });
    return;
  }

  if (!agentServiceUrl) {
    sendJson(response, 503, { detail: 'Agent non configurato.' });
    return;
  }

  const agentUrl = new URL('/api/chat', agentServiceUrl);
  const requestId = trustedRequestId(request.headers['x-request-id']);
  const identityToken = await getIdentityToken(agentUrl.origin);
  const agentResponse = await fetch(agentUrl, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${identityToken}`,
      'content-type': 'application/json',
      'x-request-id': String(requestId),
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(55_000),
  });
  const responseBody = await agentResponse.text();

  response.writeHead(agentResponse.status, {
    ...securityHeaders,
    'cache-control': 'no-store',
    'content-type': agentResponse.headers.get('content-type') || 'application/json; charset=utf-8',
    'x-request-id': agentResponse.headers.get('x-request-id') || String(requestId),
  });
  response.end(responseBody);
}

async function serveStaticFile(pathname, response) {
  const requestedPath = safeStaticPath(pathname);
  const filePath = await resolveStaticFile(requestedPath, pathname);
  const content = await readFile(filePath);
  const extension = extname(filePath).toLowerCase();
  const cacheControl = extension === '.html' ? 'no-cache' : 'public, max-age=31536000, immutable';

  response.writeHead(200, {
    ...securityHeaders,
    'cache-control': cacheControl,
    'content-type': mimeTypes[extension] || 'application/octet-stream',
  });
  response.end(content);
}

async function resolveStaticFile(filePath, pathname) {
  try {
    const fileStat = await stat(filePath);
    if (fileStat.isFile()) return filePath;
  } catch {
    // The SPA fallback below handles application routes.
  }

  if (pathname.startsWith('/assets/') || extname(pathname)) {
    throw new Error('static file not found');
  }
  return resolve(staticRoot, 'index.html');
}

function safeStaticPath(pathname) {
  const decodedPath = decodeURIComponent(pathname);
  const filePath = resolve(staticRoot, `.${decodedPath}`);
  if (filePath !== staticRoot && !filePath.startsWith(`${staticRoot}${sep}`)) {
    throw new Error('invalid static path');
  }
  return filePath;
}

function readJsonBody(request) {
  return new Promise((resolveBody, rejectBody) => {
    let size = 0;
    const chunks = [];
    let rejected = false;

    request.on('data', (chunk) => {
      if (rejected) return;
      size += chunk.length;
      if (size > maxRequestBodyBytes) {
        rejected = true;
        request.pause();
        rejectBody(new RequestBodyError(413, 'Payload troppo grande.'));
        return;
      }
      chunks.push(chunk);
    });
    request.on('end', () => {
      if (rejected) return;
      try {
        resolveBody(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch {
        rejectBody(new RequestBodyError(400, 'Payload non valido.'));
      }
    });
    request.on('error', rejectBody);
  });
}

function isValidChatPayload(payload) {
  if (!payload || typeof payload !== 'object') return false;
  if (
    typeof payload.message !== 'string' ||
    !payload.message.trim() ||
    payload.message.length > 4_000
  ) {
    return false;
  }
  if (!Array.isArray(payload.history) || payload.history.length > 12) return false;

  return payload.history.every(
    (item) =>
      item &&
      (item.role === 'assistant' || item.role === 'user') &&
      typeof item.content === 'string' &&
      Boolean(item.content.trim()) &&
      item.content.length <= 2_000,
  );
}

function trustedRequestId(value) {
  if (typeof value === 'string' && /^[A-Za-z0-9-]{1,128}$/.test(value)) return value;
  return randomUUID();
}

async function getIdentityToken(audience) {
  if (process.env.AGENT_ID_TOKEN) return process.env.AGENT_ID_TOKEN;

  if (cachedIdentityToken && cachedIdentityToken.audience === audience && cachedIdentityToken.expiresAt > Date.now()) {
    return cachedIdentityToken.value;
  }

  const metadataUrl = new URL(
    'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity',
  );
  metadataUrl.searchParams.set('audience', audience);
  const metadataResponse = await fetch(metadataUrl, {
    headers: { 'Metadata-Flavor': 'Google' },
    signal: AbortSignal.timeout(5_000),
  });
  if (!metadataResponse.ok) {
    throw new Error(`identity token request failed with status ${metadataResponse.status}`);
  }

  const value = await metadataResponse.text();
  cachedIdentityToken = {
    audience,
    expiresAt: tokenExpiry(value),
    value,
  };
  return value;
}

function tokenExpiry(token) {
  try {
    const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
    if (typeof payload.exp === 'number') return (payload.exp - 60) * 1000;
  } catch {
    // A failed parse falls back to a short cache duration.
  }
  return Date.now() + 5 * 60 * 1000;
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    ...securityHeaders,
    'cache-control': 'no-store',
    'content-type': 'application/json; charset=utf-8',
  });
  response.end(JSON.stringify(payload));
}

class RequestBodyError extends Error {
  constructor(statusCode, message) {
    super(message);
    this.statusCode = statusCode;
  }
}
