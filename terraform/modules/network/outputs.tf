output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets."
  value       = values(aws_subnet.public)[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets."
  value       = values(aws_subnet.private)[*].id
}

output "application_security_group_id" {
  description = "Application security group ID."
  value       = aws_security_group.application.id
}

output "database_security_group_id" {
  description = "Database security group ID."
  value       = aws_security_group.database.id
}