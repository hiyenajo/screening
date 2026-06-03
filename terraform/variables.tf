variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "screening-challenge"
}

variable "public_key" {
  description = "SSH public key content (e.g. cat ~/.ssh/id_rsa.pub)"
  type        = string
}

variable "my_ip_cidr" {
  description = "Your IP in CIDR notation for SSH access (e.g. 1.2.3.4/32)"
  type        = string
}

variable "slack_webhook_url" {
  description = "Slack Incoming Webhook URL (leave empty to skip Slack)"
  type        = string
  default     = ""
  sensitive   = true
}
