output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.screening.id
}

output "public_ip" {
  description = "EC2 public IP address"
  value       = aws_instance.screening.public_ip
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "ssh -i ~/.ssh/id_rsa ec2-user@${aws_instance.screening.public_ip}"
}

output "run_command" {
  description = "Command to run the W1 price check"
  value       = "ssh -i ~/.ssh/id_rsa ec2-user@${aws_instance.screening.public_ip} 'python3 ~/screening-challenge/w1_price.py'"
}
