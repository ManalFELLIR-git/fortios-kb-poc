from kb_builder.quality_gate import _validate_attribute


def test_enum_without_canonical_choices_needs_review_with_provenance():
    validation = _validate_attribute(
        {
            "canonical": {"type": "enum"},
            "evidence": {
                "cli_reference": {
                    "type": "enum",
                    "choices": ["enable", "disable"],
                }
            },
            "sources": ["cli_reference"],
        },
        exact_cli_reference=True,
    )
    assert validation["status"] == "needs_review"
    assert validation["reasons"] == ["enum_choices_missing"]
    assert validation["evidence"] == [
        {
            "source": "cli_reference",
            "observed_choices": ["enable", "disable"],
        }
    ]
