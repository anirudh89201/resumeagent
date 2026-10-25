terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~>5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }

  }
  backend "s3" {
    bucket       = "terraform-state-bucket-us-east-1-12354"
    key          = "dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }

}
variable "agentcore_role_name" {
  type=string
  default = "AmazonBedrockAgentCoreSDKRuntime-us-east-1-b47cea36db"
}
resource "aws_iam_role_policy" "agentcore_ssm_read" {
  name="ssm-read"
  role=var.agentcore_role_name
  policy = jsonencode({
    Version="2012-10-17"
    Statement=[{
      Effect="Allow"
      Action = ["ssm:GetParameter","ssm:GetParameters","ssm:GetParametersByPath"]
      Resource = [
        "arn:aws:ssm:us-east-1:${data.aws_caller_identity.current.account_id}:parameter/dev",
        "arn:aws:ssm:us-east-1:${data.aws_caller_identity.current.account_id}:parameter/dev/*"
      ]
    }]
  })
}



data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  environment = lower(terraform.workspace)
}

data "archive_file" "gateway" {
  type        = "zip"
  source_file = "${path.module}/../gateway-code/gateway_code.py"
  output_path = "${path.module}/gateway.zip"
}

resource "aws_iam_role" "gateway_lamba" {
  name = "resume-gateway-lambda-role-${local.environment}"

  assume_role_policy = jsonencode(({
    Version = "2012-10-17"
    Statement = [{
      "Effect"    = "Allow"
      "Principal" = { Service = "lambda.amazonaws.com" }
      Action      = "sts:AssumeRole"
    }]
  }))
}
resource "aws_iam_role_policy_attachment" "gatewaY-logs" {
  role       = aws_iam_role.gateway_lamba.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}


resource "aws_iam_role_policy" "gateway_access" {
  name = "resume-gateway-access"
  role = aws_iam_role.gateway_lamba.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.KB_ID_PARAM.arn
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:Retrieve"]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:knowledge-base/${aws_ssm_parameter.KB_ID_PARAM.value}"
      }
    ]
  })
}

resource "aws_s3_bucket" "resume-bucket" {
  bucket = format(
    "resume-bucket-%s-%s-%s",
    data.aws_caller_identity.current.account_id,
    data.aws_region.current.name,
    local.environment
  )
  tags = {
    Name        = "Resume bucket for connecting to KB"
    Environment = title(local.environment)
  }

}

resource "aws_s3_object" "object" {
  bucket = aws_s3_bucket.resume-bucket.id
  key    = "resume.pdf"
  source = "${path.module}/docs/anirudh_resume.pdf"
}

output "bucket_name" {
  description = "Name of the resume S3 bucket"
  value       = aws_s3_bucket.resume-bucket.id
}
resource "aws_ssm_parameter" "KB_ID_PARAM" {
  name        = "/${local.environment}/resume-kb-id/KB"
  description = "KB ID for the resume application"
  type        = "SecureString"
  value       = "PTGYVQZZTX"
}
resource "aws_ssm_parameter" "CLIENT_ID_PARAM" {
  name = "/${local.environment}/cognito_client_id"
  description = "client_id for the cognito service used my MCP client"
  type = "SecureString"
  value="jau3p4nsk5c9pnr9j99d53br8"
}
resource "aws_ssm_parameter" "CLIENT_SECRET_PARAM" {
  name = "/${local.environment}/cognito_client_secret"
  description = "client_secret for the cognito service used my MCP client"
  type = "SecureString"
  value="15o648d242a1q77c1pmtb4ao4rg5ve5cda3i9a6cl6kmdj16vb68"
} 
resource "aws_lambda_function" "test_lambda" {
  filename         = "${path.module}/gateway.zip"
  function_name    = "resume-kb-retrieve-${local.environment}"
  role             = aws_iam_role.gateway_lamba.arn
  runtime          = "python3.13"
  handler          = "gateway_code.lambda_handler"
  source_code_hash = data.archive_file.gateway.output_base64sha256

  environment {
    variables = {
      KB_ID_PARAM = aws_ssm_parameter.KB_ID_PARAM.name
    }
  }

  tags = {
    Environment = title(local.environment)
  }
}
