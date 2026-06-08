"""
Observability utilities for the online store.

Provides:
  - Structured JSON logging (logger)
  - Custom CloudWatch metrics via EMF (record_metric, track_cart_abandonment)
  - AWS X-Ray subsegment helpers (xray_subsegment)
  - Health check helpers (check_dynamodb, check_service)

Import this module in handlers that need business metrics or tracing.
"""
import json, os, logging, time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps

import boto3
from botocore.exceptions import ClientError

# ── Structured logger ─────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def log_event(event_type: str, details: dict) -> None:
    """Emit a structured JSON log entry."""
    entry = {
        'timestamp':  datetime.now(timezone.utc).isoformat(),
        'event_type': event_type,
        'environment': os.environ.get('APP_ENV', 'dev'),
        'details':    details,
    }
    logger.info(json.dumps(entry))


# ── Embedded Metric Format helpers ───────────────────────────────────────────
def _emf_metric(namespace: str, metrics: list[dict], properties: dict = None) -> None:
    """
    Print an EMF-formatted JSON object to stdout.
    CloudWatch Logs extracts the metric data automatically.

    metrics: [{"name": "CartAbandonment", "value": 1, "unit": "Count"}, ...]
    """
    metric_names = [m['name'] for m in metrics]
    payload = {
        "_aws": {
            "Timestamp":    int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace":  namespace,
                "Dimensions": [[]],
                "Metrics":    [{"Name": m['name'], "Unit": m.get('unit', 'None')}
                               for m in metrics],
            }],
        },
    }
    for m in metrics:
        payload[m['name']] = m['value']
    if properties:
        payload.update(properties)
    print(json.dumps(payload))


def record_metric(name: str, value: float, unit: str = 'Count',
                  namespace: str = 'OnlineStore/Business') -> None:
    """Publish a single custom metric via EMF."""
    _emf_metric(namespace, [{"name": name, "value": value, "unit": unit}])


def track_cart_abandonment(customer_id: str, cart_value: float,
                            reason: str = 'unknown') -> None:
    """Publish cart abandonment metrics (EMF — no extra API calls)."""
    def _value_range(v):
        if v < 50:   return 'Under50'
        if v < 100:  return '50to100'
        if v < 200:  return '100to200'
        return 'Over200'

    log_event('cart_abandoned', {'customer_id': customer_id,
                                  'cart_value': cart_value, 'reason': reason})
    _emf_metric(
        'OnlineStore/Business',
        [{"name": "CartAbandonment",  "value": 1,          "unit": "Count"},
         {"name": "AbandonedCartValue","value": cart_value, "unit": "None"}],
        properties={"reason": reason, "cart_value_range": _value_range(cart_value),
                    "customer_id": customer_id},
    )


def track_order_completed(order_id: str, customer_id: str,
                           total: float, item_count: int) -> None:
    """Publish order completion metrics."""
    log_event('order_completed', {'order_id': order_id, 'customer_id': customer_id,
                                   'total': total, 'item_count': item_count})
    _emf_metric(
        'OnlineStore/Business',
        [{"name": "OrderCompleted", "value": 1,     "unit": "Count"},
         {"name": "OrderValue",     "value": total,  "unit": "None"},
         {"name": "OrderItemCount", "value": item_count, "unit": "Count"}],
        properties={"order_id": order_id, "customer_id": customer_id},
    )


# ── X-Ray subsegment context manager ─────────────────────────────────────────
@contextmanager
def xray_subsegment(name: str, metadata: dict = None, annotations: dict = None):
    """
    Context manager that wraps a code block in an X-Ray subsegment.
    Gracefully no-ops when aws-xray-sdk is not installed (e.g. in tests).
    """
    try:
        from aws_xray_sdk.core import xray_recorder
        with xray_recorder.in_subsegment(name) as seg:
            if metadata:
                for k, v in metadata.items():
                    seg.put_metadata(k, v)
            if annotations:
                for k, v in annotations.items():
                    seg.put_annotation(k, str(v))
            yield seg
    except ImportError:
        yield None  # X-Ray SDK not installed — silently skip
    except Exception:
        yield None  # X-Ray daemon not running locally — silently skip


def xray_annotate(key: str, value) -> None:
    """Add a searchable annotation to the current X-Ray segment."""
    try:
        from aws_xray_sdk.core import xray_recorder
        xray_recorder.put_annotation(key, str(value))
    except Exception:
        pass


def xray_metadata(key: str, value) -> None:
    """Add non-indexed metadata to the current X-Ray segment."""
    try:
        from aws_xray_sdk.core import xray_recorder
        xray_recorder.put_metadata(key, value)
    except Exception:
        pass


# ── Health check helpers ──────────────────────────────────────────────────────
def check_dynamodb(table_name: str) -> dict:
    """Check DynamoDB table reachability."""
    try:
        boto3.client('dynamodb').describe_table(TableName=table_name)
        return {'status': 'healthy'}
    except ClientError as e:
        return {'status': 'unhealthy', 'error': str(e)}


def check_service(url: str, timeout: int = 3) -> dict:
    """HTTP GET health check against an external service URL."""
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return {'status': 'healthy', 'http_status': resp.status}
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}
