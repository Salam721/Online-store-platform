"""
Locust load test — simulates realistic customer behaviour.

Run against a deployed API:
  locust -f tests/performance/load_test.py --host=https://<your-api-url>

Or headless:
  locust -f tests/performance/load_test.py \
         --host=https://<your-api-url> \
         --headless -u 100 -r 10 --run-time 60s

Test types covered:
  Load test:     locust --users 100 --spawn-rate 10 --run-time 5m
  Stress test:   locust --users 500 --spawn-rate 50 --run-time 5m
  Spike test:    use custom StepShape below
  Endurance test:locust --users 50  --spawn-rate 5  --run-time 24h
"""
from locust import HttpUser, task, between, events
from locust.shape import LoadTestShape
import json, random


# ── Sample product IDs — replace with real IDs from your catalog ──────────────
PRODUCT_IDS = ['prod_001', 'prod_002', 'prod_003']
CATEGORIES  = ['Electronics', 'Audio', 'Computers', 'Accessories', 'Home']


class OnlineStoreUser(HttpUser):
    """
    Simulates a realistic customer shopping session.
    Task weights reflect typical e-commerce traffic:
      - Browse/search: ~60% of requests
      - View product:  ~25%
      - Add to cart:   ~10%
      - Checkout:       ~5%
    """
    wait_time = between(1, 3)

    @task(3)
    def browse_products(self):
        """Browse full product catalog."""
        with self.client.get('/products', catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Expected 200, got {resp.status_code}")

    @task(3)
    def browse_by_category(self):
        """Browse products filtered by category."""
        category = random.choice(CATEGORIES)
        with self.client.get(f'/products?category={category}',
                              catch_response=True, name='/products?category=[cat]') as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Expected 200, got {resp.status_code}")

    @task(2)
    def view_product(self):
        """View a specific product detail page."""
        product_id = random.choice(PRODUCT_IDS)
        with self.client.get(f'/products/{product_id}',
                              catch_response=True, name='/products/[id]') as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def track_product_view(self):
        """Track customer activity — feeds Firehose analytics."""
        product_id = random.choice(PRODUCT_IDS)
        with self.client.post('/activity',
                               json={'event_type': 'product_view',
                                     'user_id':    f'load_test_user_{random.randint(1,1000)}',
                                     'product_id': product_id,
                                     'session_id': 'load_test_session'},
                               catch_response=True) as resp:
            if resp.status_code in (200, 202):
                resp.success()
            else:
                resp.failure(f"Activity tracking failed: {resp.status_code}")

    @task(1)
    def place_order(self):
        """Place an order — most critical, lowest frequency."""
        product_id = random.choice(PRODUCT_IDS)
        with self.client.post('/orders',
                               json={'customer_id':   f'load_test_cust_{random.randint(1,500)}',
                                     'items':         [{'product_id': product_id, 'quantity': 1,
                                                        'name': 'Load Test Product'}],
                                     'total_amount':  random.uniform(10.0, 500.0),
                                     'customer_tier': 'regular',
                                     'order_type':    'standard'},
                               catch_response=True) as resp:
            if resp.status_code in (200, 202):
                resp.success()
            else:
                resp.failure(f"Order placement failed: {resp.status_code}")


class SpikeTestShape(LoadTestShape):
    """
    Spike test: normal load then sudden 10x spike then back to normal.
    Validates Auto Scaling reacts to sudden traffic increases.
    """
    stages = [
        {"duration": 60,  "users": 10,  "spawn_rate": 5},   # Normal load
        {"duration": 120, "users": 100, "spawn_rate": 50},  # Spike
        {"duration": 180, "users": 10,  "spawn_rate": 5},   # Recovery
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None  # Stop test


# ── Event hooks for custom reporting ─────────────────────────────────────────
@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               response, context, exception, **kwargs):
    if response_time > 2000:
        print(f"SLOW REQUEST: {name} took {response_time:.0f}ms")
