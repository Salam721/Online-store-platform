"""
Shared pytest fixtures for integration tests.
All fixtures use moto to mock AWS services locally — no real AWS calls.
"""
import os, json, boto3, pytest
from moto import mock_dynamodb, mock_s3, mock_sqs, mock_sns, mock_events

# ── Environment setup ─────────────────────────────────────────────────────────
os.environ.setdefault('AWS_DEFAULT_REGION',   'us-east-1')
os.environ.setdefault('AWS_ACCESS_KEY_ID',    'testing')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY','testing')
os.environ.setdefault('PRODUCTS_TABLE',       'Products')
os.environ.setdefault('ORDERS_TABLE',         'Orders')
os.environ.setdefault('PRODUCT_IMAGE_BUCKET', 'test-images-bucket')
os.environ.setdefault('ORDER_QUEUE_URL',      'https://sqs.us-east-1.amazonaws.com/123456789012/order-processing-queue')
os.environ.setdefault('CUSTOMER_NOTIFICATION_TOPIC', 'arn:aws:sns:us-east-1:123456789012:customer-notifications')
os.environ.setdefault('SYSTEM_ALERT_TOPIC',   'arn:aws:sns:us-east-1:123456789012:system-alerts')
os.environ.setdefault('INVENTORY_ALERT_TOPIC','arn:aws:sns:us-east-1:123456789012:inventory-alerts')
os.environ.setdefault('ORDER_EVENT_BUS',      'online-store-orders')
os.environ.setdefault('INVENTORY_EVENT_BUS',  'online-store-inventory')
os.environ.setdefault('ACTIVITY_STREAM_NAME', 'customer-activity-stream')
os.environ.setdefault('APP_ENV',              'test')
os.environ.setdefault('CACHE_ENDPOINT',       'localhost')
os.environ.setdefault('CACHE_PORT',           '6379')


@pytest.fixture
def aws_region():
    return 'us-east-1'


@pytest.fixture
def products_table(aws_region):
    """Create a mocked Products DynamoDB table with GSI."""
    with mock_dynamodb():
        dynamodb = boto3.resource('dynamodb', region_name=aws_region)
        table = dynamodb.create_table(
            TableName='Products',
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'id',       'AttributeType': 'S'},
                {'AttributeName': 'category', 'AttributeType': 'S'},
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'category-index',
                'KeySchema': [{'AttributeName': 'category', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'},
                'ProvisionedThroughput': {'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1},
            }],
            BillingMode='PAY_PER_REQUEST',
        )
        # Seed sample data
        table.put_item(Item={
            'id': 'prod_001', 'title': 'Wireless Headphones',
            'category': 'Electronics', 'price': '199.99',
            'description': 'High-quality wireless headphones',
            'inventory_count': 50,
        })
        table.put_item(Item={
            'id': 'prod_002', 'title': 'USB-C Cable',
            'category': 'Electronics', 'price': '12.99',
            'description': 'Fast charging USB-C cable',
            'inventory_count': 200,
        })
        table.put_item(Item={
            'id': 'prod_003', 'title': 'Desk Lamp',
            'category': 'Home', 'price': '34.99',
            'description': 'LED desk lamp with USB port',
            'inventory_count': 30,
        })
        yield table


@pytest.fixture
def orders_table(aws_region):
    """Create a mocked Orders DynamoDB table."""
    with mock_dynamodb():
        dynamodb = boto3.resource('dynamodb', region_name=aws_region)
        table = dynamodb.create_table(
            TableName='Orders',
            KeySchema=[{'AttributeName': 'order_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'order_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )
        yield table


@pytest.fixture
def images_bucket(aws_region):
    """Create a mocked S3 bucket for product images."""
    with mock_s3():
        s3 = boto3.client('s3', region_name=aws_region)
        s3.create_bucket(Bucket='test-images-bucket')
        yield s3


@pytest.fixture
def order_queue(aws_region):
    """Create a mocked SQS order processing queue."""
    with mock_sqs():
        sqs = boto3.client('sqs', region_name=aws_region)
        response = sqs.create_queue(QueueName='order-processing-queue')
        os.environ['ORDER_QUEUE_URL'] = response['QueueUrl']
        yield sqs, response['QueueUrl']


@pytest.fixture
def sns_topics(aws_region):
    """Create mocked SNS topics."""
    with mock_sns():
        sns = boto3.client('sns', region_name=aws_region)
        customer = sns.create_topic(Name='customer-notifications')
        system   = sns.create_topic(Name='system-alerts')
        inventory= sns.create_topic(Name='inventory-alerts')
        os.environ['CUSTOMER_NOTIFICATION_TOPIC'] = customer['TopicArn']
        os.environ['SYSTEM_ALERT_TOPIC']          = system['TopicArn']
        os.environ['INVENTORY_ALERT_TOPIC']       = inventory['TopicArn']
        yield {'customer': customer['TopicArn'],
               'system':   system['TopicArn'],
               'inventory':inventory['TopicArn']}


@pytest.fixture
def event_buses(aws_region):
    """Create mocked EventBridge buses."""
    with mock_events():
        eb = boto3.client('events', region_name=aws_region)
        eb.create_event_bus(Name='online-store-orders')
        eb.create_event_bus(Name='online-store-inventory')
        eb.create_event_bus(Name='online-store-customers')
        yield eb
