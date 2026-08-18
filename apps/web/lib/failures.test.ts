import { describe, expect, it } from 'vitest';
import { ApiError, SchemaError, describeFailure } from './failures';

describe('describeFailure', () => {
  it('never exposes the raw technical message as the reader-facing title', () => {
    const failure = describeFailure(new ApiError(500, 'psycopg.OperationalError: FATAL'), true);

    expect(failure.title).not.toContain('psycopg');
    expect(failure.title).not.toContain('500');
    expect(failure.technical).toContain('psycopg');
  });

  it('explains a stopped API as unreachable, with how to start it', () => {
    const failure = describeFailure(new ApiError(0, 'fetch failed'), true);

    expect(failure.title).toBe('The service cannot be reached');
    expect(failure.detail).toContain('shadow_cpi.api.main');
    expect(failure.retryable).toBe(true);
  });

  it('treats a failed fetch the same way, since that is how it surfaces', () => {
    const failure = describeFailure(new TypeError('Failed to fetch'), true);

    expect(failure.title).toBe('The service cannot be reached');
  });

  it('reports being offline ahead of anything else', () => {
    const failure = describeFailure(new ApiError(500, 'server error'), false);

    expect(failure.title).toBe('You appear to be offline');
    expect(failure.severity).toBe('degraded');
  });

  it('does not claim a reader is offline where no connection flag exists', () => {
    // Server rendering has a navigator object without an onLine flag. Reading that absence
    // as "offline" told every reader of a server-rendered page their connection had dropped.
    const original = Object.getOwnPropertyDescriptor(globalThis.navigator, 'onLine');
    Object.defineProperty(globalThis.navigator, 'onLine', {
      value: undefined,
      configurable: true,
    });

    try {
      const failure = describeFailure(new ApiError(404, 'not found'));

      expect(failure.title).toContain('Nothing has been recorded');
    } finally {
      if (original) {
        Object.defineProperty(globalThis.navigator, 'onLine', original);
      }
    }
  });

  it('says a missing entity has simply not been collected', () => {
    const failure = describeFailure(new ApiError(404, 'not found'), true);

    expect(failure.title).toContain('Nothing has been recorded');
    expect(failure.retryable).toBe(false);
  });

  it('explains a rate limit as temporary and worth retrying', () => {
    const failure = describeFailure(new ApiError(429, 'too many requests'), true);

    expect(failure.severity).toBe('degraded');
    expect(failure.retryable).toBe(true);
  });

  it('tells the reader what to create when a source has no collector', () => {
    const failure = describeFailure(new ApiError(409, 'no collector'), true);

    expect(failure.detail).toContain('SCRAPER_STUDIO_COLLECTORS');
  });

  it('describes an unready service as a startup problem, not a crash', () => {
    const failure = describeFailure(new ApiError(503, 'dependencies unavailable'), true);

    expect(failure.title).toBe('The service is not ready yet');
    expect(failure.detail).toContain('containers');
  });

  it('says a schema mismatch is a version difference, and not worth retrying', () => {
    const failure = describeFailure(new SchemaError('expected string, received null'), true);

    expect(failure.detail).toContain('different versions');
    expect(failure.retryable).toBe(false);
  });

  it('maps an unlisted server status onto the general server explanation', () => {
    const failure = describeFailure(new ApiError(502, 'bad gateway'), true);

    expect(failure.title).toBe('The service could not complete this');
  });

  it('falls back to a plain explanation for an unlisted client status', () => {
    const failure = describeFailure(new ApiError(418, 'teapot'), true);

    expect(failure.title).toBe('Something went wrong');
  });

  it('copes with something thrown that is not an error at all', () => {
    const failure = describeFailure('a string was thrown', true);

    expect(failure.title).toBe('Something went wrong');
    expect(failure.technical).toBe('a string was thrown');
  });
});
