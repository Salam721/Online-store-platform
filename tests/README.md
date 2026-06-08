# Test Suite

## Structure

```
tests/
├── unit/          # Fast tests — mocked dependencies, milliseconds each
├── integration/   # Workflow tests — moto AWS mocks, seconds each
└── performance/   # Load tests — run against deployed API with Locust
```

## Install test dependencies

```bash
pip install -r requirements-dev.txt
```

## Run all tests

```bash
pytest tests/unit tests/integration -v
```

## Run only unit tests

```bash
pytest tests/unit -v -m unit
```

## Run integration tests

```bash
pytest tests/integration -v -m integration
```

## Run deployment smoke tests (after cdk deploy)

```bash
pytest tests/integration/test_deployment.py -v
```

## Run performance / load tests

```bash
# Interactive UI at http://localhost:8089
locust -f tests/performance/load_test.py --host=https://<your-api-url>

# Headless — 100 users, 10/s ramp, 60 seconds
locust -f tests/performance/load_test.py \
       --host=https://<your-api-url> \
       --headless -u 100 -r 10 --run-time 60s

# Spike test shape
locust -f tests/performance/load_test.py \
       --host=https://<your-api-url> \
       --headless --shape-class SpikeTestShape
```

## Test coverage map

| Workflow                          | Unit | Integration | Deployment |
|-----------------------------------|------|-------------|------------|
| Product CRUD                      | ✓    | ✓           | ✓          |
| Product category query (GSI)      | ✓    | ✓           | -          |
| Image upload URL                  | ✓    | ✓           | -          |
| Order placement → SQS             | ✓    | ✓           | ✓          |
| Order processor → DynamoDB        | ✓    | ✓           | -          |
| EventBridge routing               | -    | ✓           | -          |
| Inventory decrement on order      | -    | ✓           | -          |
| SNS notification dispatch         | -    | ✓           | -          |
| DLQ for failed messages           | -    | ✓           | -          |
| Firehose activity tracking        | ✓    | ✓           | -          |
| Firehose transformation           | ✓    | -           | -          |
| Payment failure + rollback        | -    | ✓           | -          |
| Shipping failure + rollback       | -    | ✓           | -          |
| Input validation enforcement      | ✓    | -           | ✓          |
| Circuit breaker open → 503        | ✓    | -           | -          |
| Retry with exponential backoff    | ✓    | -           | -          |
| EC2 inventory API                 | ✓    | -           | -          |
| Recommendation engine             | ✓    | -           | -          |
