# Customer360 Production Deployment

## Prerequisites

Install and configure:

- Docker
- Terraform 1.6+
- AWS CLI
- kubectl
- Access to an AWS account
- GitHub repository access

## Required AWS Resources

The Terraform configuration provisions:

- VPC
- Public and private subnets
- Application and database security groups
- RDS PostgreSQL
- S3 bucket
- IAM application role

## Configure Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
