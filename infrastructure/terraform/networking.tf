# Agile Sales & Marketing - Remediated Production Networking (VPC Link + Internal ALB)
# Region: us-east-2
# VPC: vpc-0a896659fe7bea154

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "vpc_id" {
  type        = string
  default     = "vpc-0a896659fe7bea154"
  description = "Target VPC ID"
}

variable "private_subnet_ids" {
  type        = list(string)
  default     = ["subnet-057aca53b176b66bf", "subnet-02891e4f6edbb6cd9"]
  description = "Private Subnet IDs across 2 AZs (us-east-2a, us-east-2b)"
}

variable "ec2_private_ip" {
  type        = string
  default     = "10.2.1.18"
  description = "Primary private IP of the backend EC2 host (i-0104a7d71d82157f2)"
}

variable "backend_port" {
  type        = number
  default     = 8000
  description = "Port on which FastAPI backend listens"
}

# 1. VPC Link Security Group
resource "aws_security_group" "vpclink_sg" {
  name        = "agile-sales-vpclink-sg"
  description = "Security group for API Gateway VPC Link to Agile Sales internal ALB"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound traffic to VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.2.0.0/16"]
  }

  tags = {
    Name        = "agile-sales-vpclink-sg"
    Project     = "agile-sales-marketing"
    Environment = "development"
  }
}

# 2. Internal ALB Security Group
resource "aws_security_group" "internal_alb_sg" {
  name        = "agile-sales-internal-alb-sg"
  description = "Security group for Internal ALB for Agile Sales backend"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Allow port 8000 from API Gateway VPC Link"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.vpclink_sg.id]
  }

  ingress {
    description     = "Allow port 80 from API Gateway VPC Link"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.vpclink_sg.id]
  }

  egress {
    description = "Allow all outbound traffic to VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.2.0.0/16"]
  }

  tags = {
    Name        = "agile-sales-internal-alb-sg"
    Project     = "agile-sales-marketing"
    Environment = "development"
  }
}

# 3. Target Group for Backend Container
resource "aws_lb_target_group" "backend_tg" {
  name        = "agile-sales-backend-tg"
  port        = var.backend_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    port                = tostring(var.backend_port)
    protocol            = "HTTP"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
    matcher             = "200"
  }

  tags = {
    Name        = "agile-sales-backend-tg"
    Project     = "agile-sales-marketing"
    Environment = "development"
  }
}

resource "aws_lb_target_group_attachment" "backend_attachment" {
  target_group_arn  = aws_lb_target_group.backend_tg.arn
  target_id         = var.ec2_private_ip
  port              = var.backend_port
  availability_zone = "us-east-2a"
}

# 4. Internal Application Load Balancer
resource "aws_lb" "internal_alb" {
  name               = "agile-sales-internal-alb"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.internal_alb_sg.id]
  subnets            = var.private_subnet_ids

  tags = {
    Name        = "agile-sales-internal-alb"
    Project     = "agile-sales-marketing"
    Environment = "development"
  }
}

resource "aws_lb_listener" "backend_listener" {
  load_balancer_arn = aws_lb.internal_alb.arn
  port              = var.backend_port
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend_tg.arn
  }
}

# 5. API Gateway HTTP API VPC Link
resource "aws_apigatewayv2_vpc_link" "sales_vpc_link" {
  name               = "agile-sales-vpc-link"
  security_group_ids = [aws_security_group.vpclink_sg.id]
  subnet_ids         = var.private_subnet_ids

  tags = {
    Name        = "agile-sales-vpc-link"
    Project     = "agile-sales-marketing"
    Environment = "development"
  }
}
