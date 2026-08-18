/**
 * Turning failures into something a reader can act on.
 *
 * A person looking at a price screen does not need to know that a fetch rejected with
 * `ECONNREFUSED`, or that a response carried status 503. They need to know whether the
 * figures in front of them can be trusted, whether the fault is theirs, and what to do
 * next. Every failure is mapped to those three things here, in one place, so no screen
 * invents its own wording and no raw error text reaches the page.
 *
 * The technical detail is kept rather than discarded: it is shown behind a disclosure for
 * whoever is debugging, and it is what gets logged.
 */

/** How much of a screen a failure takes away. */
export type FailureSeverity = 'blocking' | 'degraded';

/**
 * A failure, described for a reader.
 */
export interface FriendlyFailure {
  /** One line, plain language, no jargon. */
  title: string;
  /** What the reader can do, or what happens next if nothing is done. */
  detail: string;
  /** Whether the screen is unusable or merely incomplete. */
  severity: FailureSeverity;
  /** The underlying message, for a developer. Never the whole story shown to a reader. */
  technical: string;
  /** Whether trying again has any chance of working. */
  retryable: boolean;
}

/** Status codes we explain individually, because each needs different advice. */
const BY_STATUS: Record<number, Omit<FriendlyFailure, 'technical'>> = {
  401: {
    title: 'This request was not authorised',
    detail:
      'The service refused the request. If you are running this locally, check that the API keys in your .env file are filled in.',
    severity: 'blocking',
    retryable: false,
  },
  403: {
    title: 'This action needs a permission you do not have',
    detail:
      'Repairing a collector requires the shared secret in CRON_SECRET. The rest of the dashboard is unaffected.',
    severity: 'blocking',
    retryable: false,
  },
  404: {
    title: 'Nothing has been recorded for this yet',
    detail:
      'The name may be spelled differently, or no collector has reported it so far. Collected entities are listed on the risk map.',
    severity: 'blocking',
    retryable: false,
  },
  409: {
    title: 'This source has no scraper attached yet',
    detail:
      'Create one with the Bright Data CLI and add its identifier to SCRAPER_STUDIO_COLLECTORS, then try again.',
    severity: 'blocking',
    retryable: false,
  },
  429: {
    title: 'Too many requests, briefly',
    detail:
      'The service limits how often it can be asked, to keep costs predictable. Wait a moment and try again.',
    severity: 'degraded',
    retryable: true,
  },
  500: {
    title: 'The service could not complete this',
    detail:
      'Something failed on the server rather than in your browser. Trying again often works; if it does not, the pipeline health screen shows what is running.',
    severity: 'blocking',
    retryable: true,
  },
  503: {
    title: 'The service is not ready yet',
    detail:
      'It usually means the databases are still starting, or a required key is missing. Check that the containers are running.',
    severity: 'blocking',
    retryable: true,
  },
  504: {
    title: 'That took too long to answer',
    detail: 'The request was still running when it timed out. Try again, or narrow the range.',
    severity: 'blocking',
    retryable: true,
  },
};

const OFFLINE: Omit<FriendlyFailure, 'technical'> = {
  title: 'You appear to be offline',
  detail: 'The figures on screen are the last ones loaded. They will refresh when you reconnect.',
  severity: 'degraded',
  retryable: true,
};

const UNREACHABLE: Omit<FriendlyFailure, 'technical'> = {
  title: 'The service cannot be reached',
  detail:
    'The dashboard loaded, but the API did not answer. If you are running this locally, start it with python -m shadow_cpi.api.main.',
  severity: 'blocking',
  retryable: true,
};

const MALFORMED: Omit<FriendlyFailure, 'technical'> = {
  title: 'The service sent something unexpected',
  detail:
    'The reply did not match what this screen expects, so it was rejected rather than displayed. This usually means the dashboard and the API are different versions.',
  severity: 'blocking',
  retryable: false,
};

const UNKNOWN: Omit<FriendlyFailure, 'technical'> = {
  title: 'Something went wrong',
  detail: 'The screen could not finish loading. Trying again is the quickest thing to rule out.',
  severity: 'blocking',
  retryable: true,
};

/**
 * Whether the runtime is actively reporting a lost connection.
 *
 * @returns True only when a browser says it is offline. A runtime with no such flag, which
 * includes server rendering, is treated as connected: absence of evidence is not evidence.
 */
function hasNavigatorReportingOffline(): boolean {
  if (typeof navigator === 'undefined') {
    return false;
  }
  const flag: unknown = navigator.onLine;
  return flag === false;
}

/**
 * An error carrying the HTTP status it came from.
 *
 * The API client throws this so callers can explain a failure without parsing message text.
 */
export class ApiError extends Error {
  /**
   * @param status - The HTTP status, or 0 when the request never got a reply.
   * @param message - The underlying technical message.
   */
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * An error raised when a reply does not match the expected schema.
 */
export class SchemaError extends Error {
  /**
   * @param message - What failed validation.
   */
  constructor(message: string) {
    super(message);
    this.name = 'SchemaError';
  }
}

/**
 * Describe any thrown value in terms a reader can act on.
 *
 * Accepts `unknown` because that is what a `catch` gives you, and because a value thrown
 * from a dependency is not guaranteed to be an `Error` at all.
 *
 * @param error - Whatever was thrown.
 * @param isOnline - Whether the browser reports a connection. Defaults to the navigator.
 * @returns The failure, described for a reader, with the technical detail kept.
 */
export function describeFailure(error: unknown, isOnline?: boolean): FriendlyFailure {
  const technical = error instanceof Error ? error.message : String(error);
  // Only an explicit false means offline. Server rendering has a navigator object without an
  // onLine flag, and treating that absence as "offline" would tell every reader of a
  // server-rendered page that their connection had dropped.
  const online = isOnline ?? !hasNavigatorReportingOffline();

  if (!online) {
    return { ...OFFLINE, technical };
  }
  if (error instanceof SchemaError) {
    return { ...MALFORMED, technical };
  }
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return { ...UNREACHABLE, technical };
    }
    const known = BY_STATUS[error.status];
    if (known) {
      return { ...known, technical };
    }
    if (error.status >= 500) {
      return { ...BY_STATUS[500], technical } as FriendlyFailure;
    }
    return { ...UNKNOWN, technical };
  }
  // A failed fetch is a TypeError in every browser, and is the shape a stopped API takes.
  if (error instanceof TypeError) {
    return { ...UNREACHABLE, technical };
  }
  return { ...UNKNOWN, technical };
}
