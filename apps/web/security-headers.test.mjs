import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSecurityHeaders } from './security-headers.mjs';

test('denies framing when no allowlist is configured', () => {
  const headers = buildSecurityHeaders('');

  assert.match(headers['content-security-policy'], /frame-ancestors 'none'/);
  assert.equal(headers['x-frame-options'], undefined);
});

test('allows self and the configured exact HTTPS origins', () => {
  const headers = buildSecurityHeaders(
    'https://wp-ndc-dev.apps.cloudpub.testedev.istat.it, https://schema.gov.it',
  );

  assert.match(
    headers['content-security-policy'],
    /frame-ancestors 'self' https:\/\/wp-ndc-dev\.apps\.cloudpub\.testedev\.istat\.it https:\/\/schema\.gov\.it/,
  );
  assert.doesNotMatch(headers['content-security-policy'], /frame-ancestors 'none'/);
  assert.equal(headers['x-frame-options'], undefined);
});

test('removes duplicate origins without broadening the policy', () => {
  const headers = buildSecurityHeaders('https://schema.gov.it,https://schema.gov.it');
  const directive = headers['content-security-policy']
    .split('; ')
    .find((item) => item.startsWith('frame-ancestors'));

  assert.equal(directive, "frame-ancestors 'self' https://schema.gov.it");
});

for (const invalidOrigin of [
  'http://schema.gov.it',
  'https://*.istat.it',
  'https://schema.gov.it/path',
  'https://schema.gov.it/',
  "https://schema.gov.it'; frame-src *",
]) {
  test(`rejects unsafe frame ancestor: ${invalidOrigin}`, () => {
    assert.throws(() => buildSecurityHeaders(invalidOrigin), /FRAME_ANCESTORS|Invalid origin/);
  });
}
