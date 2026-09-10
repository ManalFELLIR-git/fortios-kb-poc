import pytest
import requests

from kb_builder import source_resolver
from kb_builder.source_resolver import SourceResolutionError, resolve_sources


class Response:
    def __init__(self, *, text="", payload=None, status_code=200):
        self.text = text
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _mock_sources(monkeypatch, *, version="7.6.7"):
    cli_html = f"""
        <html><body><h1>FortiOS {version} CLI Reference</h1>
        <a href="/document/fortigate/{version}/cli-reference/1/config-system-global">
        config system global</a></body></html>
    """
    releases = {
        "ansible-galaxy-fortios-collection": [
            {
                "tag_name": "2.6.0",
                "name": "FortiOS collection 2.6.0",
                "body": f"Adds support for FortiOS {version}.",
                "html_url": "https://github.com/fortinet/release/2.6.0",
                "published_at": "2026-01-01T00:00:00Z",
            }
        ],
        "terraform-provider-fortios": [
            {
                "tag_name": "1.26.0",
                "name": "FortiOS provider 1.26.0",
                "body": f"Supports FortiOS {version}.",
                "html_url": "https://github.com/fortinet/release/1.26.0",
                "published_at": "2026-01-02T00:00:00Z",
            }
        ],
    }

    def get(url, **kwargs):
        if "docs.fortinet.com" in url:
            return Response(text=cli_html)
        for repository, payload in releases.items():
            if repository in url:
                return Response(payload=payload)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(source_resolver.requests, "get", get)


def test_resolve_exact_sources(monkeypatch):
    _mock_sources(monkeypatch)
    result = resolve_sources("7.6.7")
    assert result["version"] == "7.6.7"
    assert result["ansible_tag"] == "2.6.0"
    assert result["terraform_tag"] == "1.26.0"
    assert "/7.6.7/cli-reference/" in result["cli_reference_url"]
    assert {
        evidence["observed_version"]
        for evidence in result["resolution_evidence"].values()
    } == {"7.6.7"}


def test_missing_version_has_no_fallback(monkeypatch):
    _mock_sources(monkeypatch, version="7.6.7")
    with pytest.raises(SourceResolutionError, match="does not identify exact"):
        resolve_sources("9.9.9")


def test_source_error_stops_resolution(monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(source_resolver.requests, "get", unavailable)
    with pytest.raises(SourceResolutionError, match="source verification failed"):
        resolve_sources("7.6.7")
