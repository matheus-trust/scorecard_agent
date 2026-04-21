#!/usr/bin/env python3
"""Generate AWS service scorecards from structured AWS-doc research notes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aws_docs_researcher import AwsDocsResearcher, to_json


FIELD_ORDER = [
    "identity_management",
    "resource_based",
    "network_filtering",
    "encryption_at_rest",
    "encryption_in_transit",
    "aws_cloudformation",
    "aws_tag_based_abac",
    "aws_cloudwatch_events",
    "aws_vpc_endpoint",
    "aws_vpc_endpoint_policy",
]

ENCRYPTION_AT_REST_OPTIONS = {
    "customer_managed_keys": "Yes - Customer-managed keys are available<br>for {resources}",
    "aws_managed_keys_only": "Yes - Only with AWS-managed keys<br>for {resources}",
    "aws_backed_only": "AWS-backed only - No encryption option, but AWS encrypts data and configuration files on disk",
    "partial": "Partial - File configurations are encrypted, but not the data, or vice-and-versa",
    "no": "No - Encryption is not available, and data can be written on disk unencrypted",
    "na": "N/A - No data or configuration files",
}


@dataclass(frozen=True)
class FieldDefinition:
    id: str
    description: str
    instructions: str


FIELD_DEFINITIONS = OrderedDict(
    (
        item.id,
        item,
    )
    for item in [
        FieldDefinition(
            "identity_management",
            "List the security authority or authorities that manage access for the service.",
            "Set score to the service names used for managing access, usually AWS IAM.",
        ),
        FieldDefinition(
            "resource_based",
            "Whether the service supports resource-based policies on its resources.",
            'Set score to "Yes" or "No".',
        ),
        FieldDefinition(
            "network_filtering",
            "Whether any network filtering applies to the service or resource.",
            "Describe the network filtering mechanism, or set score to No if none applies.",
        ),
        FieldDefinition(
            "encryption_at_rest",
            "Whether encryption at rest is supported.",
            "Use one of the approved score templates and adapt it only where the template explicitly expects resource names.",
        ),
        FieldDefinition(
            "encryption_in_transit",
            "Whether data in transit is encrypted.",
            'Set score to "Yes" or "No".',
        ),
        FieldDefinition(
            "aws_cloudformation",
            "Whether CloudFormation supports native resources for the service.",
            'Set score to a link whose visible text is the supported resource count, for example <a href="...">10</a>. Use 0 with no link if unsupported.',
        ),
        FieldDefinition(
            "aws_tag_based_abac",
            "Whether the service supports tag-based ABAC.",
            'Set score to "Yes" or "No".',
        ),
        FieldDefinition(
            "aws_cloudwatch_events",
            "Whether activity is logged or delivered through CloudTrail.",
            'Set score to "Yes" or "No".',
        ),
        FieldDefinition(
            "aws_vpc_endpoint",
            "Whether the service supports VPC endpoints.",
            'Set score to "Yes" or "No". If there are multiple endpoint types, use Yes (<types>).',
        ),
        FieldDefinition(
            "aws_vpc_endpoint_policy",
            "Whether endpoint policies can be attached to the VPC endpoint.",
            'Set score to "Yes" or "No". If there are multiple endpoint types, score each type explicitly.',
        ),
    ]
)


def is_aws_doc_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"https"}:
        return False
    allowed_hosts = {
        "docs.aws.amazon.com",
        "aws.amazon.com",
        "docs.amazonaws.cn",
    }
    return parsed.netloc in allowed_hosts or parsed.netloc.endswith(".amazonaws.com")


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def normalize_url_list(value: Any, field_id: str) -> list[str]:
    ensure(isinstance(value, list) and value, f"{field_id}.info must be a non-empty list of AWS documentation URLs")
    urls: list[str] = []
    for item in value:
        ensure(isinstance(item, str), f"{field_id}.info entries must be strings")
        ensure(is_aws_doc_url(item), f"{field_id}.info must contain only AWS documentation URLs: {item}")
        urls.append(item)
    return urls


def render_yes_no(value: Any, field_id: str) -> str:
    ensure(isinstance(value, bool), f"{field_id}.value must be true or false")
    return "Yes" if value else "No"


def render_identity_management(payload: dict[str, Any]) -> str:
    authorities = payload.get("authorities")
    ensure(isinstance(authorities, list) and authorities, "identity_management.authorities must be a non-empty list")
    ensure(all(isinstance(item, str) and item.strip() for item in authorities), "identity_management.authorities must contain non-empty strings")
    return ", ".join(authorities)


def render_network_filtering(payload: dict[str, Any]) -> str:
    if "description" in payload:
        description = payload["description"]
        ensure(isinstance(description, str) and description.strip(), "network_filtering.description must be a non-empty string")
        return description.strip()
    value = payload.get("value")
    return render_yes_no(value, "network_filtering")


def render_encryption_at_rest(payload: dict[str, Any]) -> str:
    option = payload.get("option")
    ensure(option in ENCRYPTION_AT_REST_OPTIONS, f"encryption_at_rest.option must be one of: {', '.join(ENCRYPTION_AT_REST_OPTIONS)}")
    template = ENCRYPTION_AT_REST_OPTIONS[option]
    if "{resources}" in template:
        resources = payload.get("resources")
        ensure(isinstance(resources, list) and resources, "encryption_at_rest.resources must be a non-empty list for this option")
        ensure(all(isinstance(item, str) and item.strip() for item in resources), "encryption_at_rest.resources must contain non-empty strings")
        return template.format(resources=", ".join(resources))
    return template


def render_cloudformation(payload: dict[str, Any]) -> str:
    count = payload.get("resource_count")
    ensure(isinstance(count, int) and count >= 0, "aws_cloudformation.resource_count must be a non-negative integer")
    if count == 0:
        return "0"
    url = payload.get("resource_page")
    ensure(isinstance(url, str) and is_aws_doc_url(url), "aws_cloudformation.resource_page must be an AWS documentation URL when resource_count > 0")
    return f'<a href="{url}">{count}</a>'


def render_vpc_endpoint(payload: dict[str, Any]) -> str:
    supported = payload.get("supported")
    ensure(isinstance(supported, bool), "aws_vpc_endpoint.supported must be true or false")
    endpoint_types = payload.get("endpoint_types", [])
    if not supported:
        return "No"
    if endpoint_types:
        ensure(isinstance(endpoint_types, list), "aws_vpc_endpoint.endpoint_types must be a list")
        ensure(all(isinstance(item, str) and item.strip() for item in endpoint_types), "aws_vpc_endpoint.endpoint_types must contain non-empty strings")
        return f'Yes ({", ".join(endpoint_types)})'
    return "Yes"


def render_vpc_endpoint_policy(payload: dict[str, Any]) -> str:
    answers = payload.get("answers")
    if answers is not None:
        ensure(isinstance(answers, list) and answers, "aws_vpc_endpoint_policy.answers must be a non-empty list")
        rendered_parts: list[str] = []
        for answer in answers:
            ensure(isinstance(answer, dict), "aws_vpc_endpoint_policy.answers entries must be objects")
            endpoint_type = answer.get("endpoint_type")
            supported = answer.get("supported")
            ensure(isinstance(endpoint_type, str) and endpoint_type.strip(), "aws_vpc_endpoint_policy.answers[].endpoint_type must be a non-empty string")
            ensure(isinstance(supported, bool), "aws_vpc_endpoint_policy.answers[].supported must be true or false")
            rendered_parts.append(f'{endpoint_type}: {"Yes" if supported else "No"}')
        return ", ".join(rendered_parts)
    value = payload.get("value")
    return render_yes_no(value, "aws_vpc_endpoint_policy")


RENDERERS = {
    "identity_management": render_identity_management,
    "resource_based": lambda payload: render_yes_no(payload.get("value"), "resource_based"),
    "network_filtering": render_network_filtering,
    "encryption_at_rest": render_encryption_at_rest,
    "encryption_in_transit": lambda payload: render_yes_no(payload.get("value"), "encryption_in_transit"),
    "aws_cloudformation": render_cloudformation,
    "aws_tag_based_abac": lambda payload: render_yes_no(payload.get("value"), "aws_tag_based_abac"),
    "aws_cloudwatch_events": lambda payload: render_yes_no(payload.get("value"), "aws_cloudwatch_events"),
    "aws_vpc_endpoint": render_vpc_endpoint,
    "aws_vpc_endpoint_policy": render_vpc_endpoint_policy,
}


def build_template(service_name: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for field_id, definition in FIELD_DEFINITIONS.items():
        row: dict[str, Any] = {
            "id": field_id,
            "description": definition.description,
            "instructions": definition.instructions,
            "research": {
                "info": [
                    "https://docs.aws.amazon.com/"
                ],
                "notes": "Replace this with the exact AWS doc links and extracted evidence.",
            },
        }
        if field_id == "identity_management":
            row["research"]["authorities"] = ["AWS IAM"]
        elif field_id in {"resource_based", "encryption_in_transit", "aws_tag_based_abac", "aws_cloudwatch_events"}:
            row["research"]["value"] = True
        elif field_id == "network_filtering":
            row["research"]["description"] = "Example: Security groups on VPC endpoints"
        elif field_id == "encryption_at_rest":
            row["research"]["option"] = "customer_managed_keys"
            row["research"]["resources"] = ["Example resource"]
        elif field_id == "aws_cloudformation":
            row["research"]["resource_count"] = 1
            row["research"]["resource_page"] = "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_Example.html"
        elif field_id == "aws_vpc_endpoint":
            row["research"]["supported"] = True
            row["research"]["endpoint_types"] = ["Control plane", "Data plane"]
        elif field_id == "aws_vpc_endpoint_policy":
            row["research"]["answers"] = [
                {"endpoint_type": "Control plane", "supported": True},
                {"endpoint_type": "Data plane", "supported": False},
            ]
        rows.append(row)
    return {"service": service_name, "rows": rows}


def load_input(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def render_rows(document: dict[str, Any]) -> list[dict[str, str]]:
    rows = document.get("rows")
    ensure(isinstance(rows, list), "Input JSON must contain a rows list")

    rendered: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for row in rows:
        ensure(isinstance(row, dict), "Each row must be an object")
        field_id = row.get("id")
        ensure(field_id in FIELD_DEFINITIONS, f"Unknown id: {field_id}")
        ensure(field_id not in seen_ids, f"Duplicate id: {field_id}")
        seen_ids.add(field_id)

        research = row.get("research")
        ensure(isinstance(research, dict), f"{field_id}.research must be an object")
        info_urls = normalize_url_list(research.get("info"), field_id)
        score = RENDERERS[field_id](research)
        rendered.append(
            {
                "id": field_id,
                "score": score,
                "info": "<br>".join(info_urls),
            }
        )

    missing = [field_id for field_id in FIELD_ORDER if field_id not in seen_ids]
    ensure(not missing, f"Missing ids: {', '.join(missing)}")

    rendered.sort(key=lambda item: FIELD_ORDER.index(item["id"]))
    return rendered


def write_output(rows: list[dict[str, str]], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(rows, indent=2)

    if output_format == "markdown":
        lines = [
            "| id | score | info |",
            "| --- | --- | --- |",
        ]
        for row in rows:
            score = row["score"].replace("\n", " ")
            info = row["info"].replace("\n", " ")
            lines.append(f"| {row['id']} | {score} | {info} |")
        return "\n".join(lines)

    if output_format == "csv":
        lines = ["id,score,info"]
        for row in rows:
            values = [row["id"], row["score"], row["info"]]
            escaped = ['"' + value.replace('"', '""') + '"' for value in values]
            lines.append(",".join(escaped))
        return "\n".join(lines)

    raise ValueError(f"Unsupported output format: {output_format}")


def cmd_init(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    ensure(not output_path.exists(), f"Refusing to overwrite existing file: {output_path}")
    template = build_template(args.service)
    output_path.write_text(json.dumps(template, indent=2) + "\n")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    document = load_input(Path(args.input))
    rows = render_rows(document)
    result = write_output(rows, args.format)
    if args.output:
        Path(args.output).write_text(result + ("\n" if not result.endswith("\n") else ""))
    else:
        sys.stdout.write(result + ("\n" if not result.endswith("\n") else ""))
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    researcher = AwsDocsResearcher(args.service)
    document = researcher.build_research_document()

    if args.research_output:
        Path(args.research_output).write_text(to_json(document))

    if args.format == "research-json":
        result = to_json(document)
    else:
        rows = render_rows(document)
        result = write_output(rows, args.format)

    if args.output:
        Path(args.output).write_text(result + ("" if result.endswith("\n") else "\n"))
    else:
        sys.stdout.write(result + ("" if result.endswith("\n") else "\n"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a research template JSON file")
    init_parser.add_argument("service", help="AWS service name")
    init_parser.add_argument("-o", "--output", required=True, help="Path to the template JSON file")
    init_parser.set_defaults(func=cmd_init)

    render_parser = subparsers.add_parser("render", help="Render scorecard rows from research JSON")
    render_parser.add_argument("input", help="Path to the filled research JSON file")
    render_parser.add_argument("-f", "--format", choices=["json", "markdown", "csv"], default="markdown")
    render_parser.add_argument("-o", "--output", help="Path to write the rendered output")
    render_parser.set_defaults(func=cmd_render)

    research_parser = subparsers.add_parser("research", help="Research an AWS service directly from AWS docs")
    research_parser.add_argument("service", help="AWS service name, for example Amazon SQS")
    research_parser.add_argument(
        "-f",
        "--format",
        choices=["json", "markdown", "csv", "research-json"],
        default="markdown",
        help="Output format for the final scorecard or the intermediate research JSON",
    )
    research_parser.add_argument("-o", "--output", help="Path to write the rendered output")
    research_parser.add_argument("--research-output", help="Optional path to save the intermediate research JSON")
    research_parser.set_defaults(func=cmd_research)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
