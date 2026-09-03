const defaultFrameAncestors = "'none'";

export function buildSecurityHeaders(frameAncestorsValue = process.env.FRAME_ANCESTORS) {
  const frameAncestors = parseFrameAncestors(frameAncestorsValue);

  return {
    'content-security-policy': [
      "default-src 'self'",
      "base-uri 'self'",
      "connect-src 'self'",
      "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net",
      "form-action 'self'",
      `frame-ancestors ${frameAncestors}`,
      "img-src 'self' data:",
      "object-src 'none'",
      "script-src 'self'",
      // Angular installs component styles at runtime. Scripts remain restricted to self.
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
    ].join('; '),
    'cross-origin-opener-policy': 'same-origin',
    'permissions-policy': 'camera=(), geolocation=(), microphone=()',
    'referrer-policy': 'same-origin',
    'x-content-type-options': 'nosniff',
  };
}

function parseFrameAncestors(value) {
  if (!value?.trim()) return defaultFrameAncestors;

  const origins = value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .map(validateFrameAncestor);

  if (origins.length === 0) return defaultFrameAncestors;
  return ["'self'", ...new Set(origins)].join(' ');
}

function validateFrameAncestor(candidate) {
  if (candidate.includes('*')) {
    throw new Error('FRAME_ANCESTORS accepts exact origins only; wildcards are not allowed');
  }

  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error(`Invalid origin in FRAME_ANCESTORS: ${candidate}`);
  }

  const isExactHttpsOrigin =
    parsed.protocol === 'https:' &&
    parsed.origin === candidate &&
    parsed.pathname === '/' &&
    !parsed.search &&
    !parsed.hash &&
    !parsed.username &&
    !parsed.password;

  if (!isExactHttpsOrigin) {
    throw new Error(`FRAME_ANCESTORS requires an exact HTTPS origin: ${candidate}`);
  }
  return parsed.origin;
}
