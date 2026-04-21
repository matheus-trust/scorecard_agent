# AWS Scorecard Research Prompt

Use this prompt with a browsing-capable assistant.

## Prompt

Research the AWS service named: `<SERVICE_NAME>`

Only use AWS documentation as sources of truth. Do not use blogs, forums, marketing pages unless they are official AWS documentation pages. Every answer must include the exact AWS documentation link that proves the answer.

You must fill these scorecard ids:

- `identity_management`
- `resource_based`
- `network_filtering`
- `encryption_at_rest`
- `encryption_in_transit`
- `aws_cloudformation`
- `aws_tag_based_abac`
- `aws_cloudwatch_events`
- `aws_vpc_endpoint`
- `aws_vpc_endpoint_policy`

Definitions:

- `identity_management`: list the security authority or authorities managing access for the service. Usually AWS IAM.
- `resource_based`: whether resource-based policies are attached to resources of the service.
- `network_filtering`: whether any network filtering applies, such as security groups or ACLs.
- `encryption_at_rest`: whether encryption at rest is supported.
- `encryption_in_transit`: whether HTTPS or equivalent encryption is used in transit.
- `aws_cloudformation`: whether any resources for the service can be created natively with CloudFormation.
- `aws_tag_based_abac`: whether the service supports ABAC with tags.
- `aws_cloudwatch_events`: whether activity is logged or delivered through CloudTrail.
- `aws_vpc_endpoint`: whether the service supports VPC endpoints.
- `aws_vpc_endpoint_policy`: whether policies can be attached to the VPC endpoint.

Scoring rules:

- `identity_management`: set the score to the service names used for managing access.
- `resource_based`: use `Yes` or `No`.
- `network_filtering`: describe the filtering mechanism, or `No` if none applies.
- `encryption_at_rest`: use one of these exact templates:
  - `Yes - Customer-managed keys are available<br>for <list of resources>`
  - `Yes - Only with AWS-managed keys<br>for <list of resources>`
  - `AWS-backed only - No encryption option, but AWS encrypts data and configuration files on disk`
  - `Partial - File configurations are encrypted, but not the data, or vice-and-versa`
  - `No - Encryption is not available, and data can be written on disk unencrypted`
  - `N/A - No data or configuration files`
- `encryption_in_transit`: use `Yes` or `No`.
- `aws_cloudformation`: if supported, return HTML using the resource count as hyperlink text, for example `<a href="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_SES.html">10</a>`. If unsupported, return `0`.
- `aws_tag_based_abac`: use `Yes` or `No`.
- `aws_cloudwatch_events`: use `Yes` if CloudTrail logs or delivers events, otherwise `No`.
- `aws_vpc_endpoint`: use `Yes` or `No`. If multiple endpoint types exist, use `Yes (<types>)`.
- `aws_vpc_endpoint_policy`: use `Yes` or `No`. If multiple endpoint types exist, answer each explicitly, for example `Control plane: Yes, Data plane: No`.

Return JSON only, matching this shape exactly:

```json
{
  "service": "<SERVICE_NAME>",
  "rows": [
    {
      "id": "identity_management",
      "research": {
        "authorities": ["AWS IAM"],
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "resource_based",
      "research": {
        "value": true,
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "network_filtering",
      "research": {
        "description": "Security groups on interface VPC endpoints",
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "encryption_at_rest",
      "research": {
        "option": "customer_managed_keys",
        "resources": ["Example resource"],
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "encryption_in_transit",
      "research": {
        "value": true,
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "aws_cloudformation",
      "research": {
        "resource_count": 1,
        "resource_page": "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_Example.html",
        "info": ["https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_Example.html"]
      }
    },
    {
      "id": "aws_tag_based_abac",
      "research": {
        "value": true,
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "aws_cloudwatch_events",
      "research": {
        "value": true,
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "aws_vpc_endpoint",
      "research": {
        "supported": true,
        "endpoint_types": ["Control plane", "Data plane"],
        "info": ["https://docs.aws.amazon.com/..."]
      }
    },
    {
      "id": "aws_vpc_endpoint_policy",
      "research": {
        "answers": [
          { "endpoint_type": "Control plane", "supported": true },
          { "endpoint_type": "Data plane", "supported": false }
        ],
        "info": ["https://docs.aws.amazon.com/..."]
      }
    }
  ]
}
```

Rules:

- Return all 10 ids exactly once.
- Return JSON only, with no surrounding explanation.
- Every `info` entry must be an AWS documentation URL.
- If a field is not supported, still include the field with the correct negative value.
