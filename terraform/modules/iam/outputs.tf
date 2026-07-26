output "application_role_name" {
  description = "Application IAM role name."
  value       = aws_iam_role.application.name
}

output "application_role_arn" {
  description = "Application IAM role ARN."
  value       = aws_iam_role.application.arn
}

output "application_policy_arn" {
  description = "Application IAM policy ARN."
  value       = aws_iam_policy.application.arn
}