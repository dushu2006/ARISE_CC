// src/lib/errorHandling.ts

export interface AriseError {
  code: string;
  message: string;
  recoverable: boolean;
  retry_after?: number;
  suggested_actions?: string[];
  context: ErrorContext;
}

export interface ErrorContext {
  error_id: string;
  timestamp: string;
  component: string;
  operation: string;
  correlation_id: string;
  task_id?: string;
  agent_id?: string;
  session_id?: string;
  metadata: Record<string, any>;
}

export class AriseAPIError extends Error {
  constructor(public readonly error: AriseError) {
    super(error.message);
    this.name = 'AriseAPIError';
  }

  get isRecoverable(): boolean {
    return this.error.recoverable;
  }

  get retryAfter(): number | undefined {
    return this.error.retry_after;
  }

  get suggestedActions(): string[] {
    return this.error.suggested_actions || [];
  }

  get errorCode(): string {
    return this.error.code;
  }

  get errorContext(): ErrorContext {
    return this.error.context;
  }
}

export async function handleAPIResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json();
    throw new AriseAPIError(errorData.error);
  }
  return response.json();
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: {
    maxAttempts?: number;
    baseDelay?: number;
    onRetry?: (error: AriseAPIError, attempt: number) => Promise<void>;
  } = {}
): Promise<T> {
  const { maxAttempts = 3, baseDelay = 1000, onRetry } = options;
  let lastError: AriseAPIError;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as AriseAPIError;

      if (!lastError.isRecoverable || attempt === maxAttempts) {
        throw lastError;
      }

      const delay = baseDelay * Math.pow(2, attempt - 1) * (0.5 + Math.random());

      if (onRetry) {
        await onRetry(lastError, attempt);
      }

      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw lastError!;
}

// Result type for TypeScript (similar to Rust Result)
export type Result<T, E = AriseAPIError> =
  | { ok: true; value: T }
  | { ok: false; error: E };

export function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

export function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

export function unwrap<T, E>(result: Result<T, E>): T {
  if (!result.ok) {
    throw result.error;
  }
  return result.value;
}

export function unwrapOr<T, E>(result: Result<T, E>, defaultValue: T): T {
  return result.ok ? result.value : defaultValue;
}

export function map<T, E, U>(result: Result<T, E>, fn: (value: T) => U): Result<U, E> {
  if (result.ok) {
    return ok(fn(result.value));
  }
  return result;
}

export function mapErr<T, E, F>(result: Result<T, E>, fn: (error: E) => F): Result<T, F> {
  if (!result.ok) {
    return err(fn(result.error));
  }
  return result;
}

export function andThen<T, E, U>(result: Result<T, E>, fn: (value: T) => Result<U, E>): Result<U, E> {
  if (result.ok) {
    return fn(result.value);
  }
  return result;
}

export function isOk<T, E>(result: Result<T, E>): result is { ok: true; value: T } {
  return result.ok;
}

export function isErr<T, E>(result: Result<T, E>): result is { ok: false; error: E } {
  return !result.ok;
}

// Async result helpers
export type AsyncResult<T, E = AriseAPIError> = Promise<Result<T, E>>;

export async function tryAsync<T>(
  promise: Promise<T>,
  errorMapper?: (error: Error) => AriseAPIError
): Promise<Result<T, AriseAPIError>> {
  try {
    const value = await promise;
    return ok(value);
  } catch (error) {
    if (error instanceof AriseAPIError) {
      return err(error);
    }
    const mappedError = errorMapper
      ? errorMapper(error as Error)
      : new AriseAPIError({
          code: 'INTERNAL_ERROR',
          message: String(error),
          recoverable: false,
          context: {
            error_id: `err_${Math.random().toString(36).substring(7)}`,
            timestamp: new Date().toISOString(),
            component: 'unknown',
            operation: 'unknown',
            correlation_id: '',
            metadata: {},
          },
        });
    return err(mappedError);
  }
}

// React hook for error handling
export function useErrorHandler() {
  const handleError = (error: unknown) => {
    if (error instanceof AriseAPIError) {
      // Log to monitoring
      console.error(`[${error.error.context.error_id}] ${error.error.code}: ${error.message}`);

      // Show user-friendly message based on error code
      switch (error.error.code) {
        case 'APPROVAL_DENIED':
        case 'APPROVAL_EXPIRED':
          // Trigger approval UI
          return;
        case 'CAPABILITY_DENIED':
          // Show capability request UI
          return;
        case 'PROVIDER_UNAVAILABLE':
        case 'CIRCUIT_OPEN':
          // Show provider status
          return;
        case 'PROMPT_INJECTION_DETECTED':
        case 'AUDIT_TAMPERED':
          // Security alert
          return;
      }
    }

    // Generic error handling
    console.error('Unexpected error:', error);
  };

  return { handleError };
}

// Helper to create error context
export function createErrorContext(
  component: string,
  operation: string,
  options: {
    correlation_id?: string;
    causation_id?: string;
    task_id?: string;
    agent_id?: string;
    session_id?: string;
    metadata?: Record<string, any>;
  } = {}
): ErrorContext {
  return {
    error_id: `err_${Math.random().toString(36).substring(2, 14)}`,
    timestamp: new Date().toISOString(),
    component,
    operation,
    correlation_id: options.correlation_id || '',
    causation_id: options.causation_id || '',
    task_id: options.task_id || '',
    agent_id: options.agent_id || '',
    session_id: options.session_id || '',
    metadata: options.metadata || {},
  };
}

// Common error codes as constants
export const ErrorCodes = {
  // System
  INVALID_REQUEST: 'INVALID_REQUEST',
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  NOT_FOUND: 'NOT_FOUND',
  CONFLICT: 'CONFLICT',
  RATE_LIMITED: 'RATE_LIMITED',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
  SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
  TIMEOUT: 'TIMEOUT',

  // Task
  TASK_NOT_FOUND: 'TASK_NOT_FOUND',
  TASK_NOT_CANCELLABLE: 'TASK_NOT_CANCELLABLE',
  TASK_ALREADY_COMPLETED: 'TASK_ALREADY_COMPLETED',
  TASK_DEPENDENCY_FAILED: 'TASK_DEPENDENCY_FAILED',
  TASK_TIMEOUT: 'TASK_TIMEOUT',
  TASK_SAGA_COMPENSATION_FAILED: 'TASK_SAGA_COMPENSATION_FAILED',

  // Policy
  APPROVAL_EXPIRED: 'APPROVAL_EXPIRED',
  APPROVAL_DENIED: 'APPROVAL_DENIED',
  CAPABILITY_DENIED: 'CAPABILITY_DENIED',
  RISK_TOO_HIGH: 'RISK_TOO_HIGH',
  GRANT_EXPIRED: 'GRANT_EXPIRED',
  POLICY_NOT_FOUND: 'POLICY_NOT_FOUND',
  POLICY_CONFLICT: 'POLICY_CONFLICT',

  // Model
  PROVIDER_UNAVAILABLE: 'PROVIDER_UNAVAILABLE',
  CIRCUIT_OPEN: 'CIRCUIT_OPEN',
  MODEL_TIMEOUT: 'MODEL_TIMEOUT',
  TOKEN_LIMIT_EXCEEDED: 'TOKEN_LIMIT_EXCEEDED',
  CONTENT_FILTERED: 'CONTENT_FILTERED',
  MODEL_NOT_FOUND: 'MODEL_NOT_FOUND',
  PROVIDER_AUTH_FAILED: 'PROVIDER_AUTH_FAILED',
  PROVIDER_RATE_LIMITED: 'PROVIDER_RATE_LIMITED',

  // Voice
  WAKE_WORD_NOT_LOADED: 'WAKE_WORD_NOT_LOADED',
  ASR_FAILED: 'ASR_FAILED',
  TTS_FAILED: 'TTS_FAILED',
  SESSION_EXPIRED: 'SESSION_EXPIRED',
  AUDIO_DEVICE_ERROR: 'AUDIO_DEVICE_ERROR',
  VOICE_PIPELINE_ERROR: 'VOICE_PIPELINE_ERROR',
  BARGE_IN_FAILED: 'BARGE_IN_FAILED',

  // Memory
  MEMORY_STORE_FULL: 'MEMORY_STORE_FULL',
  PII_DETECTED: 'PII_DETECTED',
  MEMORY_NOT_FOUND: 'MEMORY_NOT_FOUND',
  CONSOLIDATION_FAILED: 'CONSOLIDATION_FAILED',
  EMBEDDING_FAILED: 'EMBEDDING_FAILED',
  VECTOR_STORE_ERROR: 'VECTOR_STORE_ERROR',
  RETENTION_POLICY_VIOLATION: 'RETENTION_POLICY_VIOLATION',

  // Agent
  AGENT_UNHEALTHY: 'AGENT_UNHEALTHY',
  AGENT_TIMEOUT: 'AGENT_TIMEOUT',
  VERIFICATION_FAILED: 'VERIFICATION_FAILED',
  DELEGATION_FAILED: 'DELEGATION_FAILED',
  AGENT_NOT_FOUND: 'AGENT_NOT_FOUND',
  COORDINATOR_UNAVAILABLE: 'COORDINATOR_UNAVAILABLE',

  // Automation
  UIA_ELEMENT_NOT_FOUND: 'UIA_ELEMENT_NOT_FOUND',
  PLAYWRIGHT_NAVIGATION_FAILED: 'PLAYWRIGHT_NAVIGATION_FAILED',
  CV_OCR_LOW_CONFIDENCE: 'CV_OCR_LOW_CONFIDENCE',
  AUTOMATION_TIMEOUT: 'AUTOMATION_TIMEOUT',
  APPLICATION_NOT_FOUND: 'APPLICATION_NOT_FOUND',
  PERMISSION_DENIED: 'PERMISSION_DENIED',

  // Security
  CREDENTIAL_NOT_FOUND: 'CREDENTIAL_NOT_FOUND',
  NETWORK_BLOCKED: 'NETWORK_BLOCKED',
  AUDIT_TAMPERED: 'AUDIT_TAMPERED',
  PROMPT_INJECTION_DETECTED: 'PROMPT_INJECTION_DETECTED',
  ENCRYPTION_FAILED: 'ENCRYPTION_FAILED',
  KEY_ROTATION_FAILED: 'KEY_ROTATION_FAILED',

  // Configuration
  CONFIG_VALIDATION_FAILED: 'CONFIG_VALIDATION_FAILED',
  SECRET_NOT_FOUND: 'SECRET_NOT_FOUND',
  FEATURE_FLAG_NOT_FOUND: 'FEATURE_FLAG_NOT_FOUND',
  MIGRATION_FAILED: 'MIGRATION_FAILED',

  // Events
  EVENT_STORE_ERROR: 'EVENT_STORE_ERROR',
  PROJECTION_ERROR: 'PROJECTION_ERROR',
  DEAD_LETTER_QUEUE_FULL: 'DEAD_LETTER_QUEUE_FULL',

  // Database
  DATABASE_CONNECTION_FAILED: 'DATABASE_CONNECTION_FAILED',
  MIGRATION_ERROR: 'MIGRATION_ERROR',
  CONSTRAINT_VIOLATION: 'CONSTRAINT_VIOLATION',
} as const;

// Type for error codes
export type ErrorCode = typeof ErrorCodes[keyof typeof ErrorCodes];