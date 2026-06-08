import time, logging, random
from enum import Enum
from threading import Lock

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"

class CircuitBreakerOpenError(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=30, success_threshold=2):
        self.failure_threshold  = failure_threshold
        self.recovery_timeout   = recovery_timeout
        self.success_threshold  = success_threshold
        self.failure_count      = 0
        self.success_count      = 0
        self.last_failure_time  = None
        self.state              = CircuitState.CLOSED
        self.lock               = Lock()

    def call(self, func, *args, **kwargs):
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info("Circuit breaker moving to HALF_OPEN")
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self):
        return (time.time() - self.last_failure_time) >= self.recovery_timeout

    def _on_success(self):
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    logger.info("Circuit breaker CLOSED after recovery")
            else:
                self.failure_count = 0

    def _on_failure(self):
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

def retry_with_exponential_backoff(func, max_retries=3, base_delay=0.1, max_delay=10):
    """Retry with equal jitter — recommended default strategy per AWS lesson."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise e
            exponential_delay = base_delay * (2 ** attempt)
            # Equal jitter: half fixed + half random
            wait_time = min((exponential_delay / 2) + random.uniform(0, exponential_delay / 2), max_delay)
            logger.warning(f"Attempt {attempt + 1} failed. Retrying in {wait_time:.2f}s")
            time.sleep(wait_time)

class ResilientExternalService:
    """Combines circuit breaker + retry with equal jitter for external services."""
    def __init__(self, service_name, failure_threshold=5, recovery_timeout=30,
                 max_retries=3, base_delay=0.1, max_delay=10):
        self.service_name    = service_name
        self.circuit_breaker = CircuitBreaker(failure_threshold, recovery_timeout)
        self.retry_config    = {"max_retries": max_retries, "base_delay": base_delay, "max_delay": max_delay}

    def call(self, func, fallback=None):
        try:
            result = self.circuit_breaker.call(
                lambda: retry_with_exponential_backoff(func, **self.retry_config)
            )
            return {"status": "success", "data": result}
        except Exception as e:
            logger.error(f"{self.service_name} failed: {str(e)}")
            if fallback:
                return {"status": "fallback", "data": fallback()}
            return {"status": "failed", "error": str(e)}

# Shared instances — reused across warm Lambda invocations
db_circuit_breaker      = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
payment_service         = ResilientExternalService("payment",  failure_threshold=5, recovery_timeout=30, max_retries=3)
shipping_service        = ResilientExternalService("shipping", failure_threshold=10, recovery_timeout=60, max_retries=2, base_delay=0.2, max_delay=3)
