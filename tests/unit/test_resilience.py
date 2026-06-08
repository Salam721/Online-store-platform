import sys, os, unittest, time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))

class TestCircuitBreaker(unittest.TestCase):
    def _make_breaker(self):
        from circuit_breaker import CircuitBreaker, CircuitState
        return CircuitBreaker(failure_threshold=3, recovery_timeout=1), CircuitState

    def test_starts_closed(self):
        breaker, CircuitState = self._make_breaker()
        self.assertEqual(breaker.state, CircuitState.CLOSED)

    def test_opens_after_threshold(self):
        breaker, CircuitState = self._make_breaker()
        for _ in range(3):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        self.assertEqual(breaker.state, CircuitState.OPEN)

    def test_half_open_after_timeout(self):
        breaker, CircuitState = self._make_breaker()
        for _ in range(3):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        time.sleep(1.1)
        try:
            breaker.call(lambda: None)
        except Exception:
            pass
        self.assertIn(breaker.state, [CircuitState.HALF_OPEN, CircuitState.CLOSED])

class TestRetryBackoff(unittest.TestCase):
    def test_retries_on_failure(self):
        from circuit_breaker import retry_with_exponential_backoff
        call_count = {'n': 0}
        def flaky():
            call_count['n'] += 1
            if call_count['n'] < 3:
                raise Exception("transient")
            return "ok"
        result = retry_with_exponential_backoff(flaky, max_retries=3, base_delay=0.01)
        self.assertEqual(result, "ok")
        self.assertEqual(call_count['n'], 3)

    def test_raises_after_max_retries(self):
        from circuit_breaker import retry_with_exponential_backoff
        with self.assertRaises(Exception):
            retry_with_exponential_backoff(lambda: (_ for _ in ()).throw(Exception("always")),
                                           max_retries=2, base_delay=0.01)

if __name__ == '__main__':
    unittest.main()
