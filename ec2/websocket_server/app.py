"""
EC2-hosted API for real-time inventory + WebSocket connections.

Chosen over Lambda/ECS because:
- WebSocket connections require persistent server processes
- Legacy inventory system needs specific runtime/library versions
- Long-running background sync jobs exceed Lambda 15-min limit
- Consistent low latency (no cold starts)

Managed by: systemd + Gunicorn (4 workers)
Load balanced by: Application Load Balancer (HTTP:80 → port 5000)
Scaled by: EC2 Auto Scaling Group (min 2, desired 2, max 10)
"""
import os, json, logging
from datetime import datetime
from flask import Flask, jsonify, request
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Persistent clients — reused across requests (EC2 advantage vs Lambda)
dynamodb      = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
products_table = dynamodb.Table(os.environ.get('PRODUCTS_TABLE', 'Products'))


# ── Health check — used by ALB target group ───────────────────────────────────
@app.route('/health')
def health_check():
    """ALB health check endpoint. Must return HTTP 200."""
    return jsonify({
        'status':    'healthy',
        'service':   'inventory-websocket-server',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }), 200


# ── Inventory endpoints ───────────────────────────────────────────────────────
@app.route('/api/products')
def get_products():
    """Return product catalog from DynamoDB."""
    try:
        response = products_table.scan()
        return jsonify(response.get('Items', []))
    except ClientError as e:
        logger.error(f"DynamoDB error: {e}")
        return jsonify({'error': 'Failed to fetch products'}), 500


@app.route('/api/products/<product_id>/inventory')
def get_inventory(product_id):
    """Return current inventory count for a product."""
    try:
        response = products_table.get_item(Key={'id': product_id})
        item = response.get('Item')
        if not item:
            return jsonify({'error': 'Product not found'}), 404
        return jsonify({
            'product_id':      product_id,
            'inventory_count': item.get('inventory_count', 0),
            'title':           item.get('title', ''),
            'updated_at':      item.get('updated_at', ''),
        })
    except ClientError as e:
        logger.error(f"DynamoDB error: {e}")
        return jsonify({'error': 'Failed to fetch inventory'}), 500


@app.route('/api/products/<product_id>/inventory', methods=['PUT'])
def update_inventory(product_id):
    """
    Update inventory count for a product.
    Long-running inventory sync jobs call this endpoint continuously —
    unsuitable for Lambda (would time out on large catalogs).
    """
    data     = request.get_json() or {}
    quantity = data.get('quantity')
    if quantity is None:
        return jsonify({'error': 'quantity is required'}), 400

    try:
        response = products_table.update_item(
            Key={'id': product_id},
            UpdateExpression='SET inventory_count = :q, updated_at = :t',
            ConditionExpression='attribute_exists(id)',
            ExpressionAttributeValues={
                ':q': int(quantity),
                ':t': datetime.utcnow().isoformat() + 'Z',
            },
            ReturnValues='ALL_NEW',
        )
        return jsonify({
            'product_id':      product_id,
            'inventory_count': int(quantity),
            'updated_at':      response['Attributes'].get('updated_at'),
        })
    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'ConditionalCheckFailedException':
            return jsonify({'error': 'Product not found'}), 404
        logger.error(f"DynamoDB error: {e}")
        return jsonify({'error': 'Failed to update inventory'}), 500


@app.route('/api/inventory/bulk', methods=['POST'])
def bulk_update_inventory():
    """
    Bulk inventory update — processes large supplier feeds.
    Can run for minutes on large catalogs; Lambda would time out.
    EC2 with systemd keeps the process alive through the full batch.
    """
    data    = request.get_json() or {}
    updates = data.get('updates', [])
    if not updates:
        return jsonify({'error': 'updates list is required'}), 400

    results = {'success': [], 'failed': []}
    for item in updates:
        product_id = item.get('product_id')
        quantity   = item.get('quantity')
        if not product_id or quantity is None:
            results['failed'].append({'product_id': product_id, 'error': 'missing fields'})
            continue
        try:
            products_table.update_item(
                Key={'id': product_id},
                UpdateExpression='SET inventory_count = :q, updated_at = :t',
                ExpressionAttributeValues={
                    ':q': int(quantity),
                    ':t': datetime.utcnow().isoformat() + 'Z',
                },
            )
            results['success'].append(product_id)
        except ClientError as e:
            logger.error(f"Failed to update {product_id}: {e}")
            results['failed'].append({'product_id': product_id, 'error': str(e)})

    return jsonify({
        'processed': len(updates),
        'success':   len(results['success']),
        'failed':    len(results['failed']),
        'results':   results,
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
