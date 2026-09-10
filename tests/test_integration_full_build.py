from pathlib import Path

from kb_builder.ansible_extractor import extract_module
from kb_builder.audit import audit
from kb_builder.fortinet_docs import parse_cli_page
from kb_builder.quality_gate import run_quality_gate
from kb_builder.reconcile import reconcile_all
from kb_builder.semantic_resolution import resolve_semantics
from kb_builder.terraform_extractor import extract_resource
from kb_builder.utils import dump_yaml, load_yaml


FIXTURES = Path(__file__).parent / "fixtures"
VERSION = "7.6.7"


def _extract_local_corpus(root: Path):
    for section, suffix in (
        ("system.sdwan", "sdwan"),
        ("system.interface", "interface"),
    ):
        ansible = extract_module(
            FIXTURES / f"fortios_system_{suffix}.py",
            VERSION,
        )
        terraform = extract_resource(
            FIXTURES / f"resource_system_{suffix}.go",
            VERSION,
        )
        cli_reference = parse_cli_page(
            (FIXTURES / f"cli_{suffix}.html").read_text(encoding="utf-8"),
            f"https://fixture.invalid/{VERSION}/{suffix}",
            VERSION,
        )
        dump_yaml(root / "raw" / "ansible" / f"{section}.yaml", ansible)
        dump_yaml(root / "raw" / "terraform" / f"{section}.yaml", terraform)
        dump_yaml(
            root / "raw" / "docs" / "cli_reference" / f"{section}.yaml",
            cli_reference,
        )


def test_offline_full_pipeline_matches_expected_yaml(tmp_path):
    _extract_local_corpus(tmp_path)
    reconcile_all(tmp_path, VERSION)
    resolve_semantics(tmp_path, VERSION, apply=True)
    quality_gate = run_quality_gate(tmp_path, VERSION)
    final_report = audit(
        tmp_path,
        VERSION,
        [],
        quality_gate_report=quality_gate,
    )

    actual_canonical = {
        path.name: load_yaml(path)
        for path in sorted((tmp_path / "canonical").glob("*.yaml"))
    }
    expected_canonical = {
        path.name: load_yaml(path)
        for path in sorted((FIXTURES / "expected_canonical").glob("*.yaml"))
    }
    assert actual_canonical == expected_canonical
    assert load_yaml(
        tmp_path / "audit" / "semantic_resolution_integrated.yaml"
    ) == load_yaml(FIXTURES / "expected_semantic_resolution.yaml")
    assert quality_gate == load_yaml(FIXTURES / "expected_quality_gate.yaml")
    assert final_report["status"] == "PARTIAL_VALIDATED"
