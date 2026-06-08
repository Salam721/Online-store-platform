# Recommendation Engine — Container Deployment

## Prerequisites
- Finch installed: `brew install finch`
- AWS CLI configured
- CDK stack deployed (creates the ECR repo)

## Build and push image

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
REPO="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/store-recommendations"

# Authenticate with ECR
aws ecr get-login-password --region $REGION \
  | finch login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com

# Build
cd containers/recommendation_engine
finch build -t recommendation-engine:latest .

# Tag and push
finch tag recommendation-engine:latest $REPO:latest
finch push $REPO:latest
```

## Test locally (without DynamoDB)

```bash
finch run --publish 8000:8000 \
  -e PRODUCTS_TABLE=Products \
  -e AWS_REGION=us-east-1 \
  recommendation-engine:latest

curl http://localhost:8000/health
curl "http://localhost:8000/recommendations?user_id=user_123&limit=3"
```

## ECS service update after pushing new image

```bash
aws ecs update-service \
  --cluster store-cluster \
  --service recommendation-service \
  --force-new-deployment
```

## Why containers for this service (not Lambda)

| Requirement                         | Lambda | Container |
|-------------------------------------|--------|-----------|
| Model training (hours)              | ✗      | ✓         |
| Warm in-memory product cache        | ✗      | ✓         |
| Persistent DynamoDB connections     | ✗      | ✓         |
| No cold start on every request      | ✗      | ✓         |
| Custom runtime dependencies         | ~      | ✓         |
