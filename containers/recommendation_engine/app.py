"""
Recommendation Engine — containerised service running on ECS/Fargate.

Chosen over Lambda because:
- Model processing can run for hours (Lambda max: 15 min)
- Maintains warm model caches in memory between requests
- Persistent connections to DynamoDB
- Consistent low-latency responses (no cold starts)
"""
import os, json, logging, random
from datetime import datetime
from flask import Flask, jsonify, request
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── AWS clients — persistent connections reused across requests ───────────────
dynamodb      = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
products_table = dynamodb.Table(os.environ.get('PRODUCTS_TABLE', 'Products'))

# ── In-memory model cache — persists between requests (container advantage) ───
_product_cache: list = []
_cache_loaded_at: str = ''


def _load_product_catalog():
    """Load full product catalog into memory for fast recommendation scoring."""
    global _product_cache, _cache_loaded_at
    try:
        response   = products_table.scan()
        _product_cache    = response.get('Items', [])
        _cache_loaded_at  = datetime.utcnow().isoformat() + 'Z'
        logger.info(f"Loaded {len(_product_cache)} products into recommendation cache")
    except ClientError as e:
        logger.error(f"Failed to load product catalog: {e}")


def _get_recommendations(user_id: str, product_id: str = None,
                          category: str = None, limit: int = 5) -> list:
    """
    Score and rank products for a given user context.
    In production this would use a trained ML model; here we use a
    rule-based heuristic to illustrate the pattern.
    """
    if not _product_cache:
        _load_product_catalog()

    candidates = list(_product_cache)

    # Filter by category if provided
    if category:
        candidates = [p for p in candidates if p.get('category') == category]

    # Exclude the product the user is currently viewing
    if product_id:
        candidates = [p for p in candidates if p.get('id') != product_id]

    # Simple scoring: shuffle to simulate model output
    random.shuffle(candidates)

    return [
        {
            'product_id':   p.get('id'),
            'title':        p.get('title', ''),
            'category':     p.get('category', ''),
            'price':        float(p.get('price', 0)),
            'score':        round(random.uniform(0.5, 1.0), 4),  # placeholder score
        }
        for p in candidates[:limit]
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/health')
def health_check():
    """ECS / ALB health check endpoint."""
    return jsonify({
        'status':           'healthy',
        'service':          'recommendation-engine',
        'products_cached':  len(_product_cache),
        'cache_loaded_at':  _cache_loaded_at,
        'timestamp':        datetime.utcnow().isoformat() + 'Z',
    })


@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    """
    GET /recommendations?user_id=<id>&product_id=<id>&category=<cat>&limit=<n>

    Returns personalised product recommendations for a user.
    """
    user_id    = request.args.get('user_id')
    product_id = request.args.get('product_id')
    category   = request.args.get('category')
    limit      = min(int(request.args.get('limit', 5)), 20)

    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400

    recommendations = _get_recommendations(user_id, product_id, category, limit)

    return jsonify({
        'user_id':         user_id,
        'recommendations': recommendations,
        'count':           len(recommendations),
        'generated_at':    datetime.utcnow().isoformat() + 'Z',
    })


@app.route('/recommendations/batch', methods=['POST'])
def get_batch_recommendations():
    """
    POST /recommendations/batch
    Body: {"user_ids": ["u1", "u2"], "limit": 5}

    Returns recommendations for multiple users in one call.
    Long-running batch operations — unsuitable for Lambda (timeout risk).
    """
    data     = request.get_json() or {}
    user_ids = data.get('user_ids', [])
    limit    = min(int(data.get('limit', 5)), 20)

    if not user_ids:
        return jsonify({'error': 'user_ids list is required'}), 400

    results = {}
    for uid in user_ids:
        results[uid] = _get_recommendations(uid, limit=limit)

    return jsonify({
        'results':      results,
        'user_count':   len(user_ids),
        'generated_at': datetime.utcnow().isoformat() + 'Z',
    })


@app.route('/cache/refresh', methods=['POST'])
def refresh_cache():
    """Force reload of the product catalog cache."""
    _load_product_catalog()
    return jsonify({
        'status':          'refreshed',
        'products_cached': len(_product_cache),
        'cache_loaded_at': _cache_loaded_at,
    })


# ── Startup ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    _load_product_catalog()  # Warm cache on startup
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
