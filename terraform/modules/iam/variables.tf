variable "project_name" {
  description = "Project name used for resource naming."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "s3_bucket_arn" {
  description = "ARN of the Customer360 S3 bucket."
  type        = string
}