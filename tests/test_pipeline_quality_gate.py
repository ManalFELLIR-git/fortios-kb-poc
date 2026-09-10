from pathlib import Path

from kb_builder import build
from kb_builder.audit import audit
from kb_builder.utils import dump_yaml, load_yaml


def _audit_fixture(tmp_path: Path, *, unresolved_types=0):
    canonical = tmp_path / "canonical"
    canonical.mkdir(parents=True)
    dump_yaml(
        canonical / "fixture.yaml",
        {
            "id": "fixture",
            "version": "7.6.7",
            "source_presence": {"cli_reference": True},
            "attributes_flat": {"name": {"canonical": {"type": "string"}}},
        },
    )
    dump_yaml(
        tmp_path / "audit" / "semantic_resolution_integrated.yaml",
        {
            "type_resolution": {
                "total": unresolved_types,
                "resolved": 0,
                "unresolved": unresolved_types,
            },
            "range_resolution": {"total": 0, "resolved": 0, "unresolved": 0},
        },
    )


def _quality_gate(*, safe=1, quarantined=0, needs_review=0):
    return {
        "version": "7.6.7",
        "total_attributes": safe + quarantined + needs_review,
        "attributes_without_validation": 0,
        "safe_attributes": safe,
        "quarantined_attributes": quarantined,
        "needs_review_attributes": needs_review,
    }


def test_audit_status_rules_and_quality_gate_report(tmp_path):
    ready = tmp_path / "ready"
    _audit_fixture(ready)
    report = audit(
        ready,
        "7.6.7",
        [],
        quality_gate_report=_quality_gate(),
    )
    assert report["status"] == "READY_FOR_GENERATION"
    assert report["kb_status"] == "READY_FOR_GENERATION"
    assert report["quality_gate"] == {
        "safe_attributes": 1,
        "quarantined_attributes": 0,
        "needs_review_attributes": 0,
    }
    assert load_yaml(ready / "audit" / "report.yaml")["status"] == "READY_FOR_GENERATION"

    partial = tmp_path / "partial"
    _audit_fixture(partial)
    report = audit(
        partial,
        "7.6.7",
        [],
        quality_gate_report=_quality_gate(
            safe=0,
            quarantined=1,
            needs_review=2,
        ),
    )
    assert report["status"] == "PARTIAL_VALIDATED"

    for name, extraction_errors, invalid_yaml, unresolved_types in (
        ("extraction", ["failed"], False, 0),
        ("invalid", [], True, 0),
        ("types", [], False, 1),
    ):
        blocked = tmp_path / name
        _audit_fixture(blocked, unresolved_types=unresolved_types)
        if invalid_yaml:
            (blocked / "canonical" / "invalid.yaml").write_text(": invalid: [", encoding="utf-8")
        report = audit(
            blocked,
            "7.6.7",
            extraction_errors,
            quality_gate_report=_quality_gate(),
        )
        assert report["status"] == "BLOCKED"


def test_build_runs_quality_gate_between_semantics_and_audit(tmp_path, monkeypatch):
    calls = []
    output = tmp_path / "output"
    config = tmp_path / "sources.yaml"
    dump_yaml(
        config,
        {
            "target": {"version": "7.6.7"},
            "sources": {
                "ansible": {"modules_dir": "modules"},
                "terraform": {"resources_dir": "resources", "docs_dir": "docs"},
                "fortinet_docs": {},
            },
        },
    )

    monkeypatch.setattr(
        build,
        "resolve_sources",
        lambda version: (
            calls.append("resolve_sources")
            or {
                "version": version,
                "cli_reference_url": (
                    f"https://docs.fortinet.com/document/fortigate/{version}/"
                    "cli-reference/84566/fortios-cli-reference"
                ),
                "ansible_tag": "2.6.0",
                "terraform_tag": "1.26.0",
                "resolution_evidence": {},
            }
        ),
    )

    monkeypatch.setattr(
        build,
        "extract_ansible",
        lambda *args: (calls.append("extract_ansible") or [], []),
    )
    monkeypatch.setattr(
        build,
        "extract_terraform",
        lambda *args: (calls.append("extract_terraform") or [], []),
    )
    monkeypatch.setattr(
        build,
        "reconcile_all",
        lambda *args: calls.append("reconcile"),
    )
    monkeypatch.setattr(
        build,
        "resolve_semantics",
        lambda *args, **kwargs: calls.append("semantic_resolution"),
    )

    quality_report = _quality_gate()

    def quality_gate(*args):
        calls.append("quality_gate")
        return quality_report

    def audit_stage(root, version, errors, quality_gate_report):
        calls.append("audit")
        assert quality_gate_report is quality_report
        return {"status": "READY_FOR_GENERATION"}

    monkeypatch.setattr(build, "run_quality_gate", quality_gate)
    monkeypatch.setattr(build, "audit", audit_stage)

    result = build.main(
        [
            "--config", str(config),
            "--version", "7.6.7",
            "--work", str(tmp_path / "work"),
            "--output", str(output),
            "--no-bootstrap",
            "--skip-docs",
        ]
    )

    assert result == 0
    assert calls == [
        "resolve_sources",
        "extract_ansible",
        "extract_terraform",
        "reconcile",
        "semantic_resolution",
        "quality_gate",
        "audit",
    ]
