from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from .fortinet_docs import UA, discover_cli_config_links


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
GITHUB_RELEASES = {
    "ansible": (
        "fortinet-ansible-dev/ansible-galaxy-fortios-collection"
    ),
    "terraform": "fortinetdev/terraform-provider-fortios",
}
CLI_REFERENCE_TEMPLATE = (
    "https://docs.fortinet.com/document/fortigate/"
    "{version}/cli-reference/84566/fortios-cli-reference"
)


class SourceResolutionError(Exception):
    pass


def _get(url: str) -> requests.Response:
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": UA,
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise SourceResolutionError(
            f"source verification failed for {url}: {exc}"
        ) from exc


def _release_mentions_exact_version(release: dict[str, Any], version: str) -> bool:
    text = " ".join(
        str(release.get(field) or "")
        for field in ("name", "body")
    )
    return bool(
        re.search(
            rf"(?<![\d.])(?:FortiOS\s*)?v?{re.escape(version)}(?!\d)",
            text,
            re.IGNORECASE,
        )
    )


def _resolve_github_release(source: str, version: str) -> tuple[str, dict]:
    repository = GITHUB_RELEASES[source]
    api_url = f"https://api.github.com/repos/{repository}/releases?per_page=100"
    try:
        releases = _get(api_url).json()
    except ValueError as exc:
        raise SourceResolutionError(
            f"{source}: official release endpoint returned invalid JSON"
        ) from exc

    if not isinstance(releases, list):
        raise SourceResolutionError(
            f"{source}: official release endpoint returned an incompatible structure"
        )

    matches = [
        release
        for release in releases
        if isinstance(release, dict)
        and release.get("tag_name")
        and _release_mentions_exact_version(release, version)
    ]
    if len(matches) != 1:
        raise SourceResolutionError(
            f"{source}: expected exactly one official release explicitly supporting "
            f"FortiOS {version}, found {len(matches)}; no fallback is allowed"
        )

    release = matches[0]
    return str(release["tag_name"]), {
        "method": "exact_version_in_official_release_metadata",
        "api_url": api_url,
        "release_url": release.get("html_url"),
        "published_at": release.get("published_at"),
        "observed_version": version,
    }


def _resolve_cli_reference(version: str) -> tuple[str, dict]:
    url = CLI_REFERENCE_TEMPLATE.format(version=version)
    response = _get(url)
    html = response.text
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    if not re.search(
        rf"(?<![\d.]){re.escape(version)}(?!\d)",
        text,
    ):
        raise SourceResolutionError(
            f"cli_reference: page does not identify exact FortiOS version {version}"
        )

    links = discover_cli_config_links(html, url, version)
    if not links:
        raise SourceResolutionError(
            "cli_reference: HTML structure is incompatible with the current parser"
        )

    return url, {
        "method": "exact_version_page_and_parser_structure",
        "url": url,
        "http_status": response.status_code,
        "observed_version": version,
        "discovered_config_links": len(links),
    }


def resolve_sources(version: str) -> dict:
    """Resolve exact sources for ``version`` or fail without a fallback."""
    version = str(version).strip()
    if not VERSION_RE.fullmatch(version):
        raise SourceResolutionError(
            f"invalid FortiOS version {version!r}; expected X.Y.Z"
        )

    cli_reference_url, cli_evidence = _resolve_cli_reference(version)
    ansible_tag, ansible_evidence = _resolve_github_release("ansible", version)
    terraform_tag, terraform_evidence = _resolve_github_release("terraform", version)

    return {
        "version": version,
        "cli_reference_url": cli_reference_url,
        "ansible_tag": ansible_tag,
        "terraform_tag": terraform_tag,
        "resolution_evidence": {
            "cli_reference": cli_evidence,
            "ansible": ansible_evidence,
            "terraform": terraform_evidence,
        },
    }
