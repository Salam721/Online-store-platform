# Deployment Guide

## IaC tool choice

| Scenario                        | Tool        | Reason                                      |
|---------------------------------|-------------|---------------------------------------------|
| Pure serverless (Lambda + APIGW)| AWS SAM     | Simplified syntax, built-in local testing   |
| Complex infra (VPC, ECS, EC2)   | **AWS CDK** | Programming language, code reuse, type safety |
| Existing CF templates           | CloudFormation | Consistency with existing stacks          |

This project uses **AWS CDK** because it includes VPC, ElastiCache, ECS, EC2, and RDS-adjacent resources.

## Environments

| Environment | Purpose                  | Parameter file            |
|-------------|--------------------------|---------------------------|
| dev         | Developer iteration      | parameters/dev.json       |
| staging     | Pre-production validation| parameters/staging.json   |
| prod        | Live customer traffic     | parameters/prod.json      |

## Deploy commands

```bash
# Activate venv
source .venv/bin/activate

# Deploy to dev (default)
cdk deploy --context environment=dev

# Deploy to staging (requires manual approval for security changes)
cdk deploy --context environment=staging --require-approval broadening

# Deploy to prod (requires manual approval for ALL changes)
cdk deploy --context environment=prod --require-approval any

# View what will change before deploying
cdk diff --context environment=prod

# Destroy dev stack (never run on staging/prod)
cdk destroy ProductApiStack-dev
```

## Feature flags

Feature flags live in `parameters/feature_flags.json`.
Upload a new version to AppConfig to change behaviour without redeployment:

```bash
# Get AppConfig IDs from stack outputs
APP_ID=$(aws appconfig list-applications --query 'Items[?Name==`online-store-prod`].Id' --output text)
ENV_ID=$(aws appconfig list-environments --application-id $APP_ID --query 'Items[?Name==`prod`].Id' --output text)
PROFILE_ID=$(aws appconfig list-configuration-profiles --application-id $APP_ID --query 'Items[?Name==`feature-flags`].Id' --output text)

# Upload updated flags (e.g. enable ai-recommendations for 25% rollout)
aws appconfig create-hosted-configuration-version \
  --application-id $APP_ID \
  --configuration-profile-id $PROFILE_ID \
  --content-type application/json \
  --content file://parameters/feature_flags.json

# Deploy the new config
aws appconfig start-deployment \
  --application-id $APP_ID \
  --environment-id $ENV_ID \
  --configuration-profile-id $PROFILE_ID \
  --configuration-version 2 \
  --deployment-strategy-id <strategy-id>
```

## Deployment strategies

| Strategy     | Command                          | Use for                         |
|--------------|----------------------------------|---------------------------------|
| All-at-once  | `cdk deploy` (default)           | Dev / low-risk config changes   |
| Blue/Green   | CodeDeploy (Module 14)           | Production Lambda deployments   |
| Canary       | AppConfig gradual rollout        | Feature flag % increases        |


## CI/CD Pipeline

### First-time setup (deploy the pipeline itself)
```bash
cdk deploy PipelineStack
```

After that, every push to the `main` branch of the CodeCommit repo
automatically runs the full pipeline.

### Pipeline stages

| Stage            | Trigger     | Action                                       |
|------------------|-------------|----------------------------------------------|
| Source           | Git push    | Pull code from CodeCommit main branch        |
| BuildAndTest     | Automatic   | Install deps, lint, unit + integration tests |
| DeployStaging    | Automatic   | `cdk deploy --context environment=staging`   |
| Approval         | Manual      | SNS email to approvers                       |
| DeployProduction | After approval | `cdk deploy --context environment=prod`   |

### Deployment strategy (prod only)

Lambda functions use **Canary 10% / 5min** via CodeDeploy:

1. Deploy new Lambda version
2. Run pre-traffic hook smoke tests
3. Shift 10% of traffic to new version
4. Wait 5 minutes — CloudWatch alarms monitor error rate and latency
5. If alarms clear → shift remaining 90%
6. Run post-traffic hook (error rate check)
7. **Auto-rollback** if any alarm fires or hook fails

### Rollback triggers (prod)

| Metric        | Threshold      | Action             |
|---------------|----------------|--------------------|
| Lambda errors | > 5 / minute   | Immediate rollback |
| p50 latency   | > 3 seconds    | Rollback after 2 periods |
| Error rate    | > 1%           | Post-hook rollback |

### Strategy selection guide

| Change type            | Strategy                    |
|------------------------|-----------------------------|
| Checkout / payment     | Blue/Green + Canary (prod)  |
| New recommendation algo| Canary via AppConfig flag   |
| Security patch         | Blue/Green (fast)           |
| Backend analytics      | Rolling / All-at-once       |
| Dev / staging          | All-at-once                 |


## Performance optimization

### Lambda memory right-sizing
```bash
# Check actual memory usage via CloudWatch Logs Insights
# (run in CW console against /aws/lambda/<fn-name>)
fields @memorySize, @maxMemoryUsed
| filter @type = "REPORT"
| stats avg(@maxMemoryUsed) as avg_mem, max(@maxMemoryUsed) as peak_mem by @memorySize
```

Recommended starting points (from parameters/*.json):
| Function type            | Dev   | Staging | Prod   |
|--------------------------|-------|---------|--------|
| Auth / health / options  | 128MB | 256MB   | 256MB  |
| Product CRUD             | 512MB | 512MB   | 1024MB |
| Order processor          | 512MB | 768MB   | 1024MB |
| Image / Firehose         | 512MB | 512MB   | 1024MB |

Use [Lambda Power Tuning](https://github.com/alexcasalboni/aws-lambda-power-tuning) to find the sweet spot.

### Load testing
```bash
npm install -g artillery@latest
artillery run artillery.yml --target https://<your-api-url>
```

### Cache hierarchy
```
Browser → CloudFront edge (staging/prod only)
        → API Gateway cache (prod: 10-min TTL)
        → Lambda L1 in-memory (per container, TTL varies)
        → Redis / ElastiCache (shared, TTL varies)
        → DynamoDB
```

### CloudFront invalidation after product update
```bash
aws cloudfront create-invalidation \
  --distribution-id <dist-id> \
  --paths "/products/<id>" "/products/<id>/image-url"
```

### DynamoDB cost tips
- Use `query` + GSI instead of `scan` for category filtering (already implemented)
- Enable TTL on session/analytics tables
- Use PAY_PER_REQUEST on dev/staging, consider PROVISIONED on prod if traffic is steady
