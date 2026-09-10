from kb_builder.quality_gate import _validate_attribute
from kb_builder.semantic_resolution import (
    description_supports_range,
    resolve_range_record,
    simple_ranges,
    units,
)


def test_range_arithmetic_units_and_min_max():
    assert simple_ranges("Allowed range is 20 - 3600 * 1000 milliseconds") == [
        (20, 3_600_000)
    ]
    assert description_supports_range("Use 20-3600000", 20, 3_600_000)
    assert units("Timeout in milliseconds") == {"milliseconds"}
    assert units("Timeout in seconds") == {"seconds"}


def test_sentinel_and_ambiguous_description():
    sentinel = resolve_range_record(
        {
            "cli_reference": {
                "min": 1,
                "max": 10,
                "default": 0,
                "description": "0 means unlimited; normal range is 1-10 seconds.",
            }
        }
    )
    assert sentinel["resolution"] == "sentinel_value_plus_normal_range"
    assert sentinel["special_values"] == [0]

    ambiguous = resolve_range_record(
        {
            "cli_reference": {
                "min": 1,
                "max": 10,
                "description": "Documented range is 2-20.",
            }
        }
    )
    assert ambiguous["status"] == "unresolved"
    assert ambiguous["resolution"] == "official_cli_internal_inconsistency"


def test_default_inside_and_outside_range():
    base = {
        "field_sources": {"type": "cli_reference"},
        "evidence": {"cli_reference": {"type": "integer"}},
        "sources": ["cli_reference"],
    }
    inside = _validate_attribute(
        {**base, "canonical": {"type": "integer", "min": 1, "max": 10, "default": 5}},
        exact_cli_reference=True,
    )
    outside = _validate_attribute(
        {**base, "canonical": {"type": "integer", "min": 1, "max": 10, "default": 11}},
        exact_cli_reference=True,
    )
    assert inside["status"] == "confirmed"
    assert outside["status"] == "needs_review"
    assert outside["reasons"] == ["default_outside_range"]
