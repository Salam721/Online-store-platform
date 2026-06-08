"""
GET /health — service health check endpoint.
Checks DynamoDB, ElastiCache, and (optionally) payment service reachability.
Returns HTTP 200 if healthy, 503 if any dependency is degraded.

Used by:
  - ALB target group health checks
  - CloudWatch Synthetics canary
  - Pre/post-deployment smoke tests
"""
import os, json, logging
from datetime import datetime, timezone
import boto3
from observability import check_dynamodb, check_service, log_event

logger = logging.getLogger(__name__)


def handler(event, context):
    status  = 'healthy'
    checks  = {}

    # ── DynamoDB ──────────────────────────────────────────────────────────────
    checks['dynamodb'] = check_dynamodb(
        os.environ.get('PRODUCTS_TABLE', 'Products'))
    if checks['dynamodb']['status'] != 'healthy':
        status = 'degraded'

    # ── ElastiCache (ping) ────────────────────────────────────────────────────
    cache_host = os.environ.get('CACHE_ENDPOINT', '')
    if cache_host and cache_host != 'localhost':
        try:
            import redis
            r = redis.Redis(host=cache_host,
                            port=int(os.environ.get('CACHE_PORT', 6379)),
                            socket_connect_timeout=2)
            r.ping()
            checks['elasticache'] = {'status': 'healthy'}
        except Exception as e:
            checks['elasticache'] = {'status': 'unhealthy', 'error': str(e)}
            status = 'degraded'
    else:
        checks['elasticache'] = {'status': 'skipped', 'reason': 'no endpoint configured'}

    # ── Payment service (optional) ────────────────────────────────────────────
    payment_url = os.environ.get('PAYMENT_HEALTH_URL', '')
    if payment_url:
        checks['payment_service'] = check_service(payment_url)
        if checks['payment_service']['status'] != 'healthy':
            status = 'degraded'

    result = {
        'service':   'online-store-api',
        'status':    status,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
        'environment': os.environ.get('APP_ENV', 'dev'),
        'checks':    checks,
    }

    log_event('health_check', {'status': status, 'checks': checks})

    return {
        'statusCode': 200 if status == 'healthy' else 503,
        'headers': {'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(result),
    }
