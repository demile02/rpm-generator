export const UPLOAD_POLL_TIMEOUT_MS = 5 * 60 * 1000;
export const UPLOAD_POLL_MAX_ATTEMPTS = 60;

export function shouldAbortPolling(startedAt: number, now = Date.now()): boolean {
  return now - startedAt >= UPLOAD_POLL_TIMEOUT_MS;
}

export function nextPollDelay(attempt: number): number {
  return Math.min(5000, 500 * Math.max(1, attempt + 1));
}
