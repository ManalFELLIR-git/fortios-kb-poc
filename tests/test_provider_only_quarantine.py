from kb_builder.quality_gate import _validate_attribute


def test_provider_only_attribute_is_quarantined():
    validation = _validate_attribute(
        {
            "canonical": {"type": "string"},
            "field_sources": {"type": "terraform"},
            "evidence": {"terraform": {"type": "string"}},
            "sources": ["terraform"],
        },
        exact_cli_reference=True,
    )
    assert validation["safe_for_cli_generation"] is False
    assert validation["status"] == "quarantined"
    assert "provider_only_candidate" in validation["reasons"]
