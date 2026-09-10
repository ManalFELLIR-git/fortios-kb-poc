from copy import deepcopy
from pathlib import Path

import yaml

from kb_builder.quality_gate import run_quality_gate


def _write_section(canonical_dir: Path, name: str, attributes: dict) -> Path:
    path = canonical_dir / f"{name}.yaml"
    path.write_text(
        yaml.safe_dump(
            {"id": name, "version": "7.6.7", "attributes_flat": attributes},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_quality_gate_annotations_and_idempotence(tmp_path):
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    attributes = {
        "confirmed": {
            "canonical": {"type": "string"},
            "field_sources": {"type": "cli_reference"},
            "evidence": {"cli_reference": {"type": "string"}},
            "sources": ["cli_reference"],
        },
        "provider_only": {
            "canonical": {"type": "string"},
            "field_sources": {"type": "terraform"},
            "evidence": {"terraform": {"type": "string"}},
            "sources": ["terraform"],
        },
        "enum_recoverable": {
            "canonical": {"type": "enum"},
            "field_sources": {"type": "cli_reference"},
            "evidence": {
                "cli_reference": {"type": "enum", "choices": ["enable", "disable"]}
            },
            "sources": ["cli_reference"],
        },
        "required_provider": {
            "canonical": {"type": "string", "required": True},
            "field_sources": {"type": "cli_reference", "required": "terraform"},
            "evidence": {
                "cli_reference": {"type": "string"},
                "terraform": {"type": "string", "required": True},
            },
            "sources": ["cli_reference", "terraform"],
        },
        "sentinel": {
            "canonical": {"type": "integer", "default": 0, "min": 1, "max": 10},
            "field_sources": {"type": "cli_reference"},
            "evidence": {"cli_reference": {"type": "integer"}},
            "sources": ["cli_reference"],
            "special_values": [0],
        },
        "outside_range": {
            "canonical": {"type": "integer", "default": 11, "min": 1, "max": 10},
            "field_sources": {"type": "cli_reference"},
            "evidence": {"cli_reference": {"type": "integer"}},
            "sources": ["cli_reference"],
        },
    }
    section_path = _write_section(canonical_dir, "fixture", deepcopy(attributes))
    _write_section(canonical_dir, "empty", {})

    first_report = run_quality_gate(tmp_path, "7.6.7")
    first_bytes = section_path.read_bytes()
    first_data = yaml.safe_load(first_bytes)
    second_report = run_quality_gate(tmp_path, "7.6.7")

    assert second_report == first_report
    assert section_path.read_bytes() == first_bytes
    assert first_report == {
        "version": "7.6.7",
        "total_attributes": 6,
        "attributes_with_validation": 6,
        "attributes_without_validation": 0,
        "safe_attributes": 2,
        "quarantined_attributes": 1,
        "needs_review_attributes": 3,
        "not_applicable_files": 1,
        "reason_counts": {
            "default_outside_range": 1,
            "enum_choices_missing": 1,
            "not_confirmed_by_exact_fortios_sources": 1,
            "provider_only_candidate": 1,
            "provider_required_only": 1,
        },
    }
    validations = {
        name: entry["validation"]
        for name, entry in first_data["attributes_flat"].items()
    }
    assert validations["confirmed"] == {
        "safe_for_cli_generation": True,
        "status": "confirmed",
        "reasons": [],
        "evidence": [{"source": "cli_reference"}],
    }
    assert validations["provider_only"]["status"] == "quarantined"
    assert validations["enum_recoverable"] == {
        "safe_for_cli_generation": False,
        "status": "needs_review",
        "reasons": ["enum_choices_missing"],
        "evidence": [
            {
                "source": "cli_reference",
                "observed_choices": ["enable", "disable"],
            }
        ],
    }
    assert validations["sentinel"]["status"] == "confirmed"
    assert validations["outside_range"]["reasons"] == ["default_outside_range"]
