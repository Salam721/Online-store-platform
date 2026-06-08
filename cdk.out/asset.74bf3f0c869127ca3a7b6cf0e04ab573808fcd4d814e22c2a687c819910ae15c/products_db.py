import boto3, boto3.dynamodb.conditions, logging
from decimal import Decimal
from datetime import datetime
from botocore.exceptions import ClientError
from circuit_breaker import db_circuit_breaker, CircuitBreakerOpenError
from config import get_products_table

logger = logging.getLogger(__name__)

def _table():
    return boto3.resource('dynamodb').Table(get_products_table())

def get_product(product_id):
    return db_circuit_breaker.call(lambda: _table().get_item(Key={'id': product_id}).get('Item'))

def get_all_products():
    return db_circuit_breaker.call(lambda: _table().scan()['Items'])

def get_products_by_category(category):
    return db_circuit_breaker.call(lambda: _table().query(
        IndexName='category-index',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('category').eq(category)
    ).get('Items'))

def insert_product(item, user_arn):
    ts = datetime.utcnow().isoformat() + 'Z'
    item.update({'created_at': ts, 'created_by': user_arn, 'updated_at': ts, 'updated_by': user_arn})
    def _put():
        try:
            _table().put_item(Item=item, ConditionExpression='attribute_not_exists(id)')
            return item
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                raise ValueError(f"Product {item['id']} already exists")
            raise
    return db_circuit_breaker.call(_put)

def update_product(product_id, fields, user_arn):
    ts   = datetime.utcnow().isoformat() + 'Z'
    expr = "SET category=:c, title=:t, description=:d, price=:p, updated_at=:ua, updated_by=:ub"
    vals = {':c': fields['category'], ':t': fields['title'], ':d': fields['description'],
            ':p': Decimal(str(fields['price'])), ':ua': ts, ':ub': user_arn}
    def _update():
        try:
            r = _table().update_item(Key={'id': product_id}, UpdateExpression=expr,
                ExpressionAttributeValues=vals, ConditionExpression='attribute_exists(id)',
                ReturnValues='ALL_NEW')
            return r['Attributes']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                raise ValueError(f"Product {product_id} does not exist")
            raise
    return db_circuit_breaker.call(_update)

def add_image_url(product_id, image_url, file_size=None):
    ts   = datetime.utcnow().isoformat() + 'Z'
    expr = "SET image_url=:img, upload_date=:d"
    vals = {':img': image_url, ':d': ts}
    if file_size:
        expr += ", file_size=:fs"
        vals[':fs'] = file_size
    db_circuit_breaker.call(lambda: _table().update_item(
        Key={'id': product_id}, UpdateExpression=expr, ExpressionAttributeValues=vals))
