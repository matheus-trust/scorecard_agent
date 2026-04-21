# AWS Service Scorecard Helper

This repo turns repeated AWS-service scorecard work into a structured workflow:

1. Research each field only from AWS documentation.
2. Record the evidence once in JSON.
3. Let the tool render your final `id`, `score`, and `info` rows using your standard templates.

If you want a browsing model to gather the evidence first, use [RESEARCH_PROMPT.md](/home/parolin/script/scorecard_agent/RESEARCH_PROMPT.md).

## What It Solves

The repetitive part of your scorecard is not the judgment, it is the formatting:

- fixed list of ids
- fixed score rules
- AWS docs only
- proof links required for every answer

`scorecard.py` standardizes that part.

It also supports direct research now: give it an AWS service name and it will try to discover the AWS documentation pages and produce the scorecard rows automatically.

## Fields Covered

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

## Usage

Create a starter template for a service:

```bash
python3 scorecard.py init "Amazon SQS" -o sqs.research.json
```

Fill in the `research` section for each row using only AWS documentation URLs.

There is also a generated sample template at [example.sqs.research.json](/home/parolin/script/scorecard_agent/example.sqs.research.json).

Render the final scorecard as Markdown:

```bash
python3 scorecard.py render sqs.research.json -f markdown
```

Render as CSV:

```bash
python3 scorecard.py render sqs.research.json -f csv -o sqs.scorecard.csv
```

Render as JSON:

```bash
python3 scorecard.py render sqs.research.json -f json -o sqs.scorecard.json
```

Research a service directly from AWS docs and render the final scorecard:

```bash
python3 scorecard.py research "Amazon SQS" -f markdown
```

Save both the rendered output and the intermediate research JSON:

```bash
python3 scorecard.py research "Amazon SQS" -f csv -o sqs.scorecard.csv --research-output sqs.research.json
```

The `research` command needs network access because it fetches AWS documentation pages live.

## Input Format

The input file contains:

- `service`: display name only
- `rows`: one object per scorecard id

Each row always has:

- `id`
- `research.info`: one or more AWS documentation URLs

Then each field has its own research shape.

### Common Examples

Boolean fields:

```json
{
  "id": "resource_based",
  "research": {
    "value": true,
    "info": [
      "https://docs.aws.amazon.com/example"
    ]
  }
}
```

Identity management:

```json
{
  "id": "identity_management",
  "research": {
    "authorities": ["AWS IAM"],
    "info": [
      "https://docs.aws.amazon.com/example"
    ]
  }
}
```

Encryption at rest:

```json
{
  "id": "encryption_at_rest",
  "research": {
    "option": "customer_managed_keys",
    "resources": ["Queues"],
    "info": [
      "https://docs.aws.amazon.com/example"
    ]
  }
}
```

Supported `encryption_at_rest.option` values:

- `customer_managed_keys`
- `aws_managed_keys_only`
- `aws_backed_only`
- `partial`
- `no`
- `na`

CloudFormation:

```json
{
  "id": "aws_cloudformation",
  "research": {
    "resource_count": 6,
    "resource_page": "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_SQS.html",
    "info": [
      "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_SQS.html"
    ]
  }
}
```

VPC endpoint support:

```json
{
  "id": "aws_vpc_endpoint",
  "research": {
    "supported": true,
    "endpoint_types": ["Control plane", "Data plane"],
    "info": [
      "https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-privatelink-support.html"
    ]
  }
}
```

VPC endpoint policy support by endpoint type:

```json
{
  "id": "aws_vpc_endpoint_policy",
  "research": {
    "answers": [
      { "endpoint_type": "Control plane", "supported": true },
      { "endpoint_type": "Data plane", "supported": false }
    ],
    "info": [
      "https://docs.aws.amazon.com/example"
    ]
  }
}
```

## Validation Rules

The tool validates:

- all 10 ids are present exactly once
- `info` is non-empty for every row
- `info` links are HTTPS AWS documentation URLs
- each field follows the required input structure

## Output Shape

Rendered output always contains:

- `id`
- `score`
- `info`

`score` is formatted using your standard rules.

## Notes

- The tool does not invent evidence.
- The tool does not use non-AWS sources.
- The tool is intentionally strict so bad citations or malformed rows are caught early.
- The `research` command uses best-effort discovery and heuristics over AWS documentation pages, so it is much faster than manual work but you should still spot-check the output for edge-case services.
