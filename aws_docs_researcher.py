#!/usr/bin/env python3
"""AWS documentation discovery and scorecard research helpers."""

from __future__ import annotations

import html
import json
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


USER_AGENT = "scorecard-agent/0.1 (+https://docs.aws.amazon.com/)"
DDG_HTML_SEARCH = "https://html.duckduckgo.com/html/"
PRIVATELINK_URL = "https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-privatelink-support.html"
IAM_SERVICES_URL = "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_aws-services-that-work-with-iam.html"
EVENTBRIDGE_CLOUDTRAIL_URL = "https://docs.aws.amazon.com/eventbridge/latest/userguide/logging-using-cloudtrail.html"
CLOUDFORMATION_INDEX_URL = "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html"
CLOUDTRAIL_INDEX_URL = "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-supported-services.html"


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    lowered = value.lower()
    lowered = lowered.replace("amazon ", "")
    lowered = lowered.replace("aws ", "")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return normalize_space(lowered)


def short_service_token(value: str) -> str:
    parts = slugify(value).split()
    return "".join(parts)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = normalize_space("".join(self._text_parts))
            self.links.append((self._href, text))
            self._href = None
            self._text_parts = []


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append(normalize_space("".join(self._cell_parts)))
            self._cell_parts = None
        elif tag == "tr" and self._table is not None and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = normalize_space(data)
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


@dataclass
class SearchResult:
    url: str
    title: str


@dataclass
class HtmlPage:
    url: str
    html: str
    text: str
    tables: list[list[list[str]]]
    links: list[tuple[str, str]]


class HttpClient:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.ssl_context = ssl.create_default_context()

    def get(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")


class AwsDocsResearcher:
    def __init__(self, service_name: str, http_client: HttpClient | None = None) -> None:
        self.service_name = service_name.strip()
        self.service_slug = slugify(service_name)
        self.service_token = short_service_token(service_name)
        self.http = http_client or HttpClient()
        self._page_cache: dict[str, HtmlPage] = {}
        self._search_cache: dict[str, list[SearchResult]] = {}
        self._resolved_links: dict[str, str | None] = {}

    def search_docs(self, query: str, limit: int = 8) -> list[SearchResult]:
        cached = self._search_cache.get(query)
        if cached is not None:
            return cached

        params = urllib.parse.urlencode({"q": query})
        html_doc = self.http.get(f"{DDG_HTML_SEARCH}?{params}")
        parser = LinkCollector()
        parser.feed(html_doc)

        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for href, text in parser.links:
            if not href or "duckduckgo.com" in href:
                continue
            resolved = urllib.parse.urlsplit(href)
            if resolved.netloc == "duckduckgo.com":
                qs = urllib.parse.parse_qs(resolved.query)
                href = qs.get("uddg", [href])[0]
            href = html.unescape(href)
            if not href.startswith("https://docs.aws.amazon.com/"):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            results.append(SearchResult(url=href, title=text))
            if len(results) >= limit:
                break

        self._search_cache[query] = results
        return results

    def fetch_page(self, url: str) -> HtmlPage:
        cached = self._page_cache.get(url)
        if cached is not None:
            return cached

        html_doc = self.http.get(url)
        text_parser = TextExtractor()
        text_parser.feed(html_doc)
        table_parser = TableParser()
        table_parser.feed(html_doc)
        link_parser = LinkCollector()
        link_parser.feed(html_doc)
        page = HtmlPage(
            url=url,
            html=html_doc,
            text=text_parser.text(),
            tables=table_parser.tables,
            links=link_parser.links,
        )
        self._page_cache[url] = page
        return page

    def first_page(self, query: str) -> HtmlPage | None:
        results = self.search_docs(query, limit=5)
        return self.fetch_page(results[0].url) if results else None

    def best_result(self, query: str, preferred_terms: list[str] | None = None, limit: int = 8) -> SearchResult | None:
        preferred_terms = preferred_terms or []
        results = self.search_docs(query, limit=limit)
        if not results:
            return None

        def score(result: SearchResult) -> tuple[int, int]:
            haystack = f"{result.title} {result.url}"
            normalized = slugify(haystack)
            compact = normalized.replace(" ", "")
            value = 0
            if self.service_token and self.service_token in compact:
                value += 20
            if self.service_slug and self.service_slug in normalized:
                value += 20
            for term in preferred_terms:
                if not term:
                    continue
                term_slug = slugify(term)
                if term_slug and term_slug in normalized:
                    value += 10
            if "/latest/" in result.url:
                value += 4
            if "amazonaws.com" in result.url:
                value += 2
            return value, -results.index(result)

        return max(results, key=score)

    def best_page(self, query: str, preferred_terms: list[str] | None = None, limit: int = 8) -> HtmlPage | None:
        result = self.best_result(query, preferred_terms=preferred_terms, limit=limit)
        return self.fetch_page(result.url) if result else None

    def _matches_service(self, value: str) -> bool:
        normalized = slugify(value)
        if not normalized:
            return False
        return self.service_slug in normalized or normalized in self.service_slug or self.service_token in normalized.replace(" ", "")

    def _pick_service_link(self, page: HtmlPage, kind: str) -> str | None:
        cached = self._resolved_links.get(kind)
        if kind in self._resolved_links:
            return cached

        best_url: str | None = None
        best_score = -1
        for href, text in page.links:
            absolute = urllib.parse.urljoin(page.url, href)
            haystack = f"{text} {absolute}"
            normalized = slugify(haystack)
            compact = normalized.replace(" ", "")
            score = 0
            if self.service_token and self.service_token in compact:
                score += 20
            if self.service_slug and self.service_slug in normalized:
                score += 15
            if self._matches_service(text):
                score += 15
            if "/latest/" in absolute:
                score += 3
            if not absolute.startswith("https://docs.aws.amazon.com/"):
                score -= 20
            if text.lower() in {"yes", "no", "partial"}:
                score -= 10
            if score > best_score:
                best_score = score
                best_url = absolute

        if best_score < 10:
            best_url = None
        self._resolved_links[kind] = best_url
        return best_url

    def _service_iam_page(self) -> HtmlPage | None:
        index = self.fetch_page(IAM_SERVICES_URL)
        url = self._pick_service_link(index, "iam")
        return self.fetch_page(url) if url else None

    def _iam_service_row(self) -> list[str] | None:
        index = self.fetch_page(IAM_SERVICES_URL)
        if not index.tables:
            return None
        for row in index.tables[0][1:]:
            if row and self._matches_service(row[0]):
                return row
        return None

    def _service_privatelink_page(self) -> HtmlPage | None:
        index = self.fetch_page(PRIVATELINK_URL)
        url = self._pick_service_link(index, "privatelink")
        return self.fetch_page(url) if url else None

    def _service_cloudformation_page(self) -> HtmlPage | None:
        index = self.fetch_page(CLOUDFORMATION_INDEX_URL)
        url = self._pick_service_link(index, "cloudformation")
        return self.fetch_page(url) if url else None

    def _service_cloudtrail_page(self) -> HtmlPage | None:
        index = self.fetch_page(CLOUDTRAIL_INDEX_URL)
        url = self._pick_service_link(index, "cloudtrail")
        return self.fetch_page(url) if url else None

    def _candidate_service_pages(self) -> list[HtmlPage]:
        pages: list[HtmlPage] = []
        seen: set[str] = set()

        for page in [self._service_iam_page(), self._service_privatelink_page(), self._service_cloudtrail_page()]:
            if page and page.url not in seen:
                seen.add(page.url)
                pages.append(page)

        if pages:
            base_page = pages[0]
            for relative in ["welcome.html", "data-protection.html", "security.html", "security-iam.html"]:
                url = urllib.parse.urljoin(base_page.url, relative)
                try:
                    page = self.fetch_page(url)
                except Exception:
                    continue
                title = page.text.splitlines()[0] if page.text else ""
                if "page not found" in title.lower():
                    continue
                if (self._matches_service(title) or "/latest/" in url) and url not in seen:
                    seen.add(url)
                    pages.append(page)

        return pages

    def _keyword_link_pages(self, keywords: list[str]) -> list[HtmlPage]:
        pages: list[HtmlPage] = []
        seen: set[str] = set()
        lowered_keywords = [keyword.lower() for keyword in keywords]
        for source_page in self._candidate_service_pages():
            for href, text in source_page.links:
                haystack = f"{text} {href}".lower()
                if not any(keyword in haystack for keyword in lowered_keywords):
                    continue
                absolute = urllib.parse.urljoin(source_page.url, href)
                if not absolute.startswith("https://docs.aws.amazon.com/") or absolute in seen:
                    continue
                try:
                    page = self.fetch_page(absolute)
                except Exception:
                    continue
                seen.add(absolute)
                pages.append(page)
        return pages

    def _iam_feature_support(self, feature_name: str) -> tuple[str, str] | None:
        page = self._service_iam_page()
        if page is None:
            return None

        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            if feature_name.lower() in line.lower():
                for probe in [line, *(lines[index + 1:index + 3])]:
                    match = re.search(r"\b(Yes|No|Partial)\b", probe, flags=re.IGNORECASE)
                    if match:
                        return match.group(1).title(), page.url
        table_text = page.text
        match = re.search(rf"{re.escape(feature_name)}.*?\b(Yes|No|Partial)\b", table_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).title(), page.url
        return None

    def research_identity_management(self) -> dict[str, Any]:
        page = self._service_iam_page()
        info = [page.url] if page else [IAM_SERVICES_URL]
        return {"authorities": ["AWS IAM"], "info": info}

    def research_resource_based(self) -> dict[str, Any]:
        row = self._iam_service_row()
        if row and len(row) >= 4:
            return {"value": row[3] == "Yes", "info": [IAM_SERVICES_URL]}
        support = self._iam_feature_support("Resource-based policies")
        return {"value": support is not None and support[0] == "Yes", "info": [support[1] if support else IAM_SERVICES_URL]}

    def research_tag_based_abac(self) -> dict[str, Any]:
        row = self._iam_service_row()
        if row and len(row) >= 5:
            return {"value": row[4] in {"Yes", "Partial"}, "info": [IAM_SERVICES_URL]}
        support = self._iam_feature_support("ABAC")
        value = support is not None and support[0] in {"Yes", "Partial"}
        return {"value": value, "info": [support[1] if support else IAM_SERVICES_URL]}

    def research_cloudtrail(self) -> dict[str, Any]:
        page = self._service_cloudtrail_page()
        if page is not None and "cloudtrail" in page.text.lower():
            return {"value": True, "info": [page.url]}
        return {"value": False, "info": [EVENTBRIDGE_CLOUDTRAIL_URL]}

    def research_cloudformation(self) -> dict[str, Any]:
        page = self._service_cloudformation_page()
        if page is not None:
            resource_types = sorted(set(re.findall(r"AWS::[A-Za-z0-9]+::[A-Za-z0-9]+", page.text)))
            if resource_types:
                return {
                    "resource_count": len(resource_types),
                    "resource_page": page.url,
                    "info": [page.url],
                }
        return {"resource_count": 0, "info": []}

    def _privatelink_rows(self) -> list[list[str]]:
        page = self.fetch_page(PRIVATELINK_URL)
        rows: list[list[str]] = []
        for table in page.tables:
            if not table:
                continue
            header = " | ".join(table[0]).lower()
            if "aws service" in header and "service name" in header:
                rows.extend(table[1:])
        return rows

    def _privatelink_match(self) -> tuple[list[str], str] | None:
        for row in self._privatelink_rows():
            if not row:
                continue
            service_cell = row[0]
            if self._matches_service(service_cell):
                names = [item for item in row[1:] if item]
                return names, PRIVATELINK_URL
        return None

    def research_vpc_endpoint(self) -> dict[str, Any]:
        match = self._privatelink_match()
        if not match:
            return {"supported": False, "info": [PRIVATELINK_URL]}
        endpoint_names, info_url = match
        page = self._service_privatelink_page()
        if page is not None:
            info_url = page.url
        endpoint_types = endpoint_names if endpoint_names else []
        return {"supported": True, "endpoint_types": endpoint_types, "info": [info_url]}

    def research_vpc_endpoint_policy(self) -> dict[str, Any]:
        vpc_match = self._privatelink_match()
        if not vpc_match:
            return {"value": False, "info": [PRIVATELINK_URL]}

        endpoint_names, _ = vpc_match
        page = self._service_privatelink_page()
        if page is not None and "endpoint policy" in page.text.lower():
            info_url = page.url
            if endpoint_names and len(endpoint_names) > 1:
                return {
                    "answers": [{"endpoint_type": name, "supported": True} for name in endpoint_names],
                    "info": [info_url],
                }
            return {"value": True, "info": [info_url]}
        if endpoint_names and len(endpoint_names) > 1:
            return {
                "answers": [{"endpoint_type": name, "supported": False} for name in endpoint_names],
                "info": [PRIVATELINK_URL],
            }
        return {"value": False, "info": [PRIVATELINK_URL]}

    def research_network_filtering(self) -> dict[str, Any]:
        match = self._privatelink_match()
        if match:
            endpoint_names, _ = match
            page = self._service_privatelink_page()
            info_url = page.url if page else PRIVATELINK_URL
            description = "Security groups on interface VPC endpoints"
            if any("s3" in name.lower() or "dynamodb" in name.lower() for name in endpoint_names):
                description = "VPC endpoint policies and route-table controls on gateway endpoints"
            return {"description": description, "info": [info_url]}
        for page in self._candidate_service_pages():
            text = page.text.lower()
            if "security groups" in text:
                return {"description": "Security groups", "info": [page.url]}
        return {"value": False, "info": [IAM_SERVICES_URL]}

    def research_encryption_in_transit(self) -> dict[str, Any]:
        for page in self._candidate_service_pages():
            text = page.text.lower()
            if "https" in text or "tls" in text or "ssl" in text:
                return {"value": True, "info": [page.url]}
        return {"value": False, "info": [IAM_SERVICES_URL]}

    def research_encryption_at_rest(self) -> dict[str, Any]:
        pages = self._candidate_service_pages() + self._keyword_link_pages(["encryption", "sse", "server-side", "data encryption"])
        for page in pages:
            text = page.text.lower()
            if "customer managed key" in text or "customer-managed key" in text or "customer managed kms key" in text or "create and manage aws kms keys yourself" in text:
                return {
                    "option": "customer_managed_keys",
                    "resources": [self.service_name],
                    "info": [page.url],
                }
            if "aws managed key" in text or "aws-managed key" in text or "alias/aws/" in text:
                return {
                    "option": "aws_managed_keys_only",
                    "resources": [self.service_name],
                    "info": [page.url],
                }
            if "encrypted at rest by default" in text or "encrypts your data at rest" in text:
                return {"option": "aws_backed_only", "info": [page.url]}
            if "not support encryption at rest" in text or "unencrypted" in text:
                return {"option": "no", "info": [page.url]}
        return {"option": "na", "info": [IAM_SERVICES_URL]}

    def build_research_document(self) -> dict[str, Any]:
        cloudformation = self.research_cloudformation()
        if not cloudformation.get("info"):
            cloudformation["info"] = ["https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/"]

        rows = [
            {"id": "identity_management", "research": self.research_identity_management()},
            {"id": "resource_based", "research": self.research_resource_based()},
            {"id": "network_filtering", "research": self.research_network_filtering()},
            {"id": "encryption_at_rest", "research": self.research_encryption_at_rest()},
            {"id": "encryption_in_transit", "research": self.research_encryption_in_transit()},
            {"id": "aws_cloudformation", "research": cloudformation},
            {"id": "aws_tag_based_abac", "research": self.research_tag_based_abac()},
            {"id": "aws_cloudwatch_events", "research": self.research_cloudtrail()},
            {"id": "aws_vpc_endpoint", "research": self.research_vpc_endpoint()},
            {"id": "aws_vpc_endpoint_policy", "research": self.research_vpc_endpoint_policy()},
        ]
        return {"service": self.service_name, "rows": rows}


def to_json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2) + "\n"
