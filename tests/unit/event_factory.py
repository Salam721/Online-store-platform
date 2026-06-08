class APIGatewayEventFactory:
    @staticmethod
    def get(path_params=None, query_params=None, body=None, headers=None):
        return {
            'httpMethod': 'GET',
            'pathParameters': path_params or {},
            'queryStringParameters': query_params or {},
            'body': body,
            'headers': headers or {},
            'requestContext': {'identity': {'userArn': 'arn:aws:iam::123:user/test'}},
        }

    @staticmethod
    def post(body=None, headers=None):
        return {
            'httpMethod': 'POST',
            'pathParameters': {},
            'queryStringParameters': {},
            'body': body,
            'headers': headers or {},
            'requestContext': {'identity': {'userArn': 'arn:aws:iam::123:user/test'}},
        }
