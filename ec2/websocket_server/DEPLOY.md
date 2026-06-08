# Inventory WebSocket Server — EC2 Deployment

## Why EC2 (not Lambda or ECS)

| Requirement                              | Lambda | ECS    | EC2    |
|------------------------------------------|--------|--------|--------|
| WebSocket persistent connections         | ✗      | ✓      | ✓      |
| Bulk jobs > 15 min                       | ✗      | ✓      | ✓      |
| Specific OS / legacy lib versions        | ✗      | ~      | ✓      |
| Full OS-level control                    | ✗      | ✗      | ✓      |
| Cost-effective for 24/7 steady traffic   | ✗      | ✓      | ✓      |

## Prerequisites
- EC2 key pair created in AWS console
- CDK stack deployed (creates instance, ALB, ASG)

## Connect to instance

### Session Manager (recommended — no SSH keys, full audit log)
```bash
aws ssm start-session --target <instance-id>
```

### SSH (development)
```bash
chmod 400 my-key.pem
ssh -i my-key.pem ec2-user@<public-ip>
```

## Manual setup on instance

```bash
# Update and install
sudo yum update -y
sudo yum install -y python3 python3-pip git

# Create venv
python3 -m venv ~/venv
source ~/venv/bin/activate
pip install flask gunicorn boto3

# Copy app files
mkdir -p ~/app
# scp or git clone your app here

# Install systemd service
sudo cp myapi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable myapi
sudo systemctl start myapi
sudo systemctl status myapi
```

## Monitor

```bash
# Live logs
sudo journalctl -u myapi -f

# Check CPU credits (T3 instances)
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUCreditBalance \
  --dimensions Name=InstanceId,Value=<instance-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 --statistics Average
```

## Deploy updates

```bash
# On the instance
cd ~/app
git pull origin main
pip install -r requirements.txt
sudo systemctl restart myapi
```

## Test endpoints

```bash
ALB_URL="http://<alb-dns-name>"
curl "$ALB_URL/health"
curl "$ALB_URL/api/products"
curl "$ALB_URL/api/products/prod_001/inventory"
curl -X PUT "$ALB_URL/api/products/prod_001/inventory" \
  -H "Content-Type: application/json" \
  -d '{"quantity": 50}'
```
