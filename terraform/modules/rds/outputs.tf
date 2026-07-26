output "endpoint" {
  description = "RDS PostgreSQL endpoint."
  value       = aws_db_instance.this.endpoint
}

output "address" {
  description = "RDS PostgreSQL hostname."
  value       = aws_db_instance.this.address
}

output "port" {
  description = "RDS PostgreSQL port."
  value       = aws_db_instance.this.port
}

output "database_name" {
  description = "PostgreSQL database name."
  value       = aws_db_instance.this.db_name
}

output "database_username" {
  description = "PostgreSQL administrator username."
  value       = aws_db_instance.this.username
  sensitive   = true
}

output "database_password" {
  description = "Generated PostgreSQL administrator password."
  value       = random_password.database.result
  sensitive   = true
}