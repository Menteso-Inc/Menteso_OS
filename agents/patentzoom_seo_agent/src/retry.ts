export interface RetryOptions {
  retries?: number;
  delayMs?: number;
  backoffMultiplier?: number;
  onRetry?: (attempt: number, error: unknown) => void | Promise<void>;
}

export async function withRetry<T>(
  run: () => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const retries = options.retries ?? 3;
  let delayMs = options.delayMs ?? 1000;
  const backoff = options.backoffMultiplier ?? 2;
  let lastError: unknown;

  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      return await run();
    } catch (error) {
      lastError = error;
      if (attempt >= retries) break;
      if (options.onRetry) await options.onRetry(attempt, error);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      delayMs *= backoff;
    }
  }

  throw lastError;
}

