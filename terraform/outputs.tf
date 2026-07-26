output "vpc_id" {
  description = "Customer360 VPC ID."
  value       = module.network.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = module.network.private_subnet_ids
}

output "application_security_group_id" {
  description = "Application security group ID."
  value       = module.network.application_security_group_id
}

output "database_endpoint" {
  description = "RDS PostgreSQL endpoint."
  value       = module.rds.endpoint
}

output "database_name" {
  description = "RDS PostgreSQL database name."
  value       = module.rds.database_name
}

output "database_username" {
  description = "RDS PostgreSQL administrator username."
  value       = module.rds.database_username
  sensitive   = true
}

output "database_password" {
  description = "Generated RDS PostgreSQL administrator password."
  value       = module.rds.database_password
  sensitive   = true
}

output "s3_bucket_name" {
  description = "Customer360 S3 bucket name."
  value       = module.s3.bucket_name
}

output "application_role_arn" {
  description = "Customer360 application IAM role ARN."
  value       = module.iam.application_role_arn
}