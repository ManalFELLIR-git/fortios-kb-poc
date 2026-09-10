from kb_builder.quality_gate import _validate_attribute


def test_provider_required_is_not_treated_as_os_required():
    validation = _validate_attribute(
        {
            "canonical": {"type": "string", "required": True},
            "field_sources": {"type": "cli_reference", "required": "terraform"},
            "evidence": {
                "cli_reference": {"type": "string"},
                "terraform": {"type": "string", "required": True},
            },
            "sources": ["cli_reference", "terraform"],
        },
        exact_cli_reference=True,
    )
    assert validation == {
        "safe_for_cli_generation": False,
        "status": "needs_review",
        "reasons": ["provider_required_only"],
        "evidence": [
            {"source": "cli_reference"},
            {"source": "terraform"},
        ],
    }
