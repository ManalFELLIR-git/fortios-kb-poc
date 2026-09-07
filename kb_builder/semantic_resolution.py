from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import re

from .utils import load_yaml, dump_yaml


BASE_TYPES = {
    "string",
    "integer",
    "boolean",
    "float",
    "number",
    "object",
    "list",
    "set",
    "enum",
}

COLLECTION_TYPES = {
    "list",
    "set",
    "object",
}


# ============================================================
# COMMON
# ============================================================

def norm_type(value):

    if value is None:
        return None

    value = str(value).strip().lower()

    aliases = {
        "int": "integer",
        "bool": "boolean",
        "dict": "object",
        "array": "list",
    }

    return aliases.get(
        value,
        value,
    )


def norm_id(value):

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").lower(),
    )


def number(value):

    try:
        return Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return None


def number_text(value):

    value = number(value)

    if value is None:
        return None

    if value == value.to_integral():
        return str(int(value))

    return format(
        value,
        "f",
    )


# ============================================================
# TERRAFORM DUAL REPRESENTATION INDEX
# ============================================================

def get_tf_attributes(data):

    attrs = data.get(
        "attributes",
        {},
    )

    result = set()

    if isinstance(attrs, dict):

        result.update(
            str(k)
            for k in attrs
        )

    elif isinstance(attrs, list):

        for item in attrs:

            if isinstance(item, str):
                result.add(item)

            elif isinstance(item, dict):

                for key in (
                    "name",
                    "attribute",
                    "id",
                    "path",
                    "source_attribute",
                ):

                    value = item.get(key)

                    if isinstance(
                        value,
                        str,
                    ):
                        result.add(value)
                        break

    return result


def build_tf_index(root: Path):

    raw_tf = (
        root
        / "raw"
        / "terraform"
    )

    result = defaultdict(
        list
    )

    for path in raw_tf.glob(
        "*.yaml"
    ):

        try:
            data = load_yaml(
                path
            )

        except Exception:
            continue

        if not isinstance(
            data,
            dict,
        ):
            continue

        sid = (
            data.get("id")
            or data.get("section_id")
            or path.stem
        )

        result[
            norm_id(sid)
        ].append({
            "id":
                sid,

            "path":
                str(path),

            "attributes":
                get_tf_attributes(
                    data
                ),
        })

    return result


# ============================================================
# TYPE CLASSIFICATION
# ============================================================

def classify_type_conflict(
    values,
):

    values = {
        src: norm_type(value)
        for src, value
        in values.items()
        if value is not None
    }

    unique = set(
        values.values()
    )


    # --------------------------------------------
    # object vs Terraform list container
    # --------------------------------------------

    if (
        unique
        <= COLLECTION_TYPES
        and "object" in unique
        and (
            "list" in unique
            or "set" in unique
        )
    ):

        return (
            "object_container_representation"
        )


    # --------------------------------------------
    # collection vs scalar element representation
    # --------------------------------------------

    has_collection = any(
        x in COLLECTION_TYPES
        for x in unique
    )

    has_scalar = any(
        x not in COLLECTION_TYPES
        for x in unique
    )

    if (
        has_collection
        and has_scalar
    ):

        return (
            "collection_vs_element_type"
        )


    # --------------------------------------------
    # Fortinet specialized CLI type
    # --------------------------------------------

    cli_type = values.get(
        "cli_reference"
    )

    other_types = {
        value
        for source, value
        in values.items()
        if source
        != "cli_reference"
    }

    if (
        cli_type
        and (
            cli_type not in BASE_TYPES
            or (
                cli_type == "enum"
                and "integer"
                in other_types
            )
        )
    ):

        return "needs_review"


    return "scalar_type_conflict"


# ============================================================
# TYPE SEMANTIC RESOLUTION
# ============================================================

def semantic_type_resolution(
    classification,
    values,
):

    values = {
        source: norm_type(value)
        for source, value
        in values.items()
    }


    if (
        classification
        == "object_container_representation"
    ):

        return {
            "resolution":
                "compatible_representation",

            "semantic_type": {
                "kind":
                    "object",

                "container_representation":
                    values.get(
                        "terraform"
                    ),
            },

            "confidence":
                "high",
        }


    if (
        classification
        == "collection_vs_element_type"
    ):

        scalar_types = {
            value
            for value
            in values.values()
            if value not in {
                "list",
                "set",
                "object",
            }
        }

        element_type = (
            next(
                iter(
                    scalar_types
                )
            )
            if len(
                scalar_types
            ) == 1
            else None
        )

        return {
            "resolution":
                "compatible_representation",

            "semantic_type": {
                "element_type":
                    element_type,

                "cardinality":
                    "multiple",
            },

            "confidence":
                "high"
                if element_type
                else "medium",
        }


    if (
        classification
        == "needs_review"
    ):

        cli_type = values.get(
            "cli_reference"
        )

        other_types = {
            value
            for source, value
            in values.items()
            if source
            != "cli_reference"
        }


        if (
            cli_type
            and cli_type
            not in BASE_TYPES
            and other_types
            and other_types
            == {"string"}
        ):

            semantic = {
                "primitive":
                    "string",

                "format":
                    cli_type,
            }

            if (
                "password"
                in cli_type
            ):
                semantic[
                    "sensitive"
                ] = True

            return {
                "resolution":
                    "compatible_specialization",

                "semantic_type":
                    semantic,

                "authority":
                    "cli_reference",

                "confidence":
                    "high",
            }


        if (
            cli_type == "enum"
            and "integer"
            in other_types
        ):

            return {
                "resolution":
                    "enum_numeric_representation_review",

                "semantic_type": {
                    "kind":
                        "enum",
                },

                "confidence":
                    "needs_review",
            }


    return {
        "resolution":
            "scalar_type_conflict",

        "confidence":
            "needs_review",
    }


def detect_dual_tf_representation(
    tf_index,
    section,
    attribute,
):

    base_attr = (
        str(attribute)
        .split(".")[-1]
    )

    companion = (
        base_attr
        + "_string"
    )

    detected = []

    for candidate in tf_index.get(
        norm_id(section),
        [],
    ):

        attrs = {
            str(a)
            for a
            in candidate[
                "attributes"
            ]
        }

        if (
            base_attr in attrs
            and companion in attrs
        ):

            detected.append({
                "terraform_section":
                    candidate["id"],

                "base_attribute":
                    base_attr,

                "string_companion":
                    companion,

                "file":
                    candidate["path"],
            })

    return detected


# ============================================================
# RANGE HELPERS
# ============================================================

def simple_ranges(text):

    if not text:
        return []

    pattern = re.compile(
        r"(?<![\d.])"
        r"(-?\d+(?:\.\d+)?)"
        r"\s*(?:-|–|—|to)\s*"
        r"(-?\d+(?:\.\d+)?)"
        r"(?:\s*\*\s*(-?\d+(?:\.\d+)?))?"
        r"(?![\d.])",
        re.I,
    )

    result = []

    for match in pattern.finditer(
        str(text)
    ):

        a = number(
            match.group(1)
        )

        b = number(
            match.group(2)
        )

        multiplier = (
            number(
                match.group(3)
            )
            if match.group(3)
            else None
        )

        if (
            b is not None
            and multiplier
            is not None
        ):
            b = (
                b
                * multiplier
            )

        if (
            a is not None
            and b is not None
        ):
            result.append(
                (
                    a,
                    b,
                )
            )

    return result


def description_supports_range(
    description,
    min_value,
    max_value,
):

    mn = number(
        min_value
    )

    mx = number(
        max_value
    )

    if (
        mn is None
        or mx is None
    ):
        return False

    return (
        (
            mn,
            mx,
        )
        in simple_ranges(
            description
        )
    )


def units(text):

    text = str(
        text or ""
    ).lower()

    groups = {

        "milliseconds": (
            "millisecond",
            "milliseconds",
            "msec",
        ),

        "seconds": (
            " second",
            " seconds",
            " sec",
        ),

        "minutes": (
            "minute",
            "minutes",
        ),

        "hours": (
            "hour",
            "hours",
        ),

        "days": (
            "day",
            "days",
        ),

        "kbps": (
            "kbps",
        ),

        "bytes": (
            "byte",
            "bytes",
        ),
    }

    result = set()

    for canonical, names in (
        groups.items()
    ):

        if any(
            name in text
            for name in names
        ):
            result.add(
                canonical
            )

    return result


def explicit_platform_dependency(
    text,
):

    text = str(
        text or ""
    ).lower()

    phrases = (
        "depend on the number of cpu",
        "depends on the number of cpu",
        "depend on the model",
        "depends on the model",
        "depending on the model",
        "number of cpus",
        "number of cpu cores",
        "only available on fortigate units with multiple cpus",
        "hardware dependent",
        "platform dependent",
    )

    return any(
        phrase in text
        for phrase in phrases
    )


def explicit_zero_special(
    text,
):

    text = str(
        text or ""
    ).lower()

    patterns = (
        r"\b0\b\s+means\s+",
        r"\b0\b\s*=\s*",
        r"\b0\b\s*-\s*always",
        r"\b0\b\s+to\s+disable",
        r"\b0\b.*unlimited",
        r"default value of zero means",
    )

    return any(
        re.search(
            pattern,
            text,
        )
        for pattern in patterns
    )


# ============================================================
# RANGE RESOLUTION
# ============================================================

def resolve_range_record(
    evidence,
):

    cli = evidence.get(
        "cli_reference",
        {},
    )

    tf = evidence.get(
        "terraform",
        {},
    )

    ans = evidence.get(
        "ansible",
        {},
    )


    cli_desc = str(
        cli.get(
            "description",
            "",
        )
    )

    ans_desc = str(
        ans.get(
            "description",
            "",
        )
    )


    cli_min = cli.get(
        "min"
    )

    cli_max = cli.get(
        "max"
    )

    tf_min = tf.get(
        "min"
    )

    tf_max = tf.get(
        "max"
    )


    ans_ranges = simple_ranges(
        ans_desc
    )


    ans_supports_cli = (
        description_supports_range(
            ans_desc,
            cli_min,
            cli_max,
        )
    )


    ans_supports_tf = (
        description_supports_range(
            ans_desc,
            tf_min,
            tf_max,
        )
    )


    cli_units = units(
        cli_desc
    )

    ans_units = units(
        ans_desc
    )


    unit_mismatch = (
        bool(cli_units)
        and bool(ans_units)
        and cli_units.isdisjoint(
            ans_units
        )
    )


    combined_desc = (
        cli_desc
        + " "
        + ans_desc
    )


    platform = (
        explicit_platform_dependency(
            combined_desc
        )
    )


    zero_special = (
        explicit_zero_special(
            combined_desc
        )
    )


    cli_default = number(
        cli.get(
            "default"
        )
    )

    mn = number(
        cli_min
    )

    mx = number(
        cli_max
    )


    default_outside_range = False

    if (
        cli_default
        is not None
        and mn is not None
        and mx is not None
    ):

        default_outside_range = (
            cli_default < mn
            or cli_default > mx
        )


    cli_ranges_detected = (
        simple_ranges(
            cli_desc
        )
    )


    cli_structured_range = None

    if (
        mn is not None
        and mx is not None
    ):

        cli_structured_range = (
            mn,
            mx,
        )


    cli_internal_inconsistency = (
        bool(
            cli_ranges_detected
        )
        and cli_structured_range
        is not None
        and cli_structured_range
        not in cli_ranges_detected
    )


    special_values = []

    if (
        zero_special
        or (
            default_outside_range
            and cli_default == 0
        )
    ):
        special_values.append(
            0
        )


    # --------------------------------------------------------
    # Tested rule order
    # --------------------------------------------------------

    if (
        cli_internal_inconsistency
    ):

        resolution = (
            "official_cli_internal_inconsistency"
        )

        status = "unresolved"
        confidence = "needs_review"
        canonical_policy = None


    elif platform:

        resolution = (
            "platform_dependent_range"
        )

        status = "resolved"
        confidence = "high"

        canonical_policy = (
            "cli_reference_base_range_"
            "plus_hardware_overlay"
        )


    elif unit_mismatch:

        resolution = (
            "unit_or_semantic_disagreement"
        )

        status = "unresolved"
        confidence = "needs_review"
        canonical_policy = None


    elif special_values:

        resolution = (
            "sentinel_value_plus_normal_range"
        )

        status = "resolved"
        confidence = "high"

        canonical_policy = (
            "cli_reference_normal_range_"
            "plus_special_values"
        )


    elif (
        ans_supports_cli
        and not ans_supports_tf
    ):

        resolution = (
            "terraform_constraint_mismatch"
        )

        status = "resolved"
        confidence = "high"

        canonical_policy = (
            "prefer_exact_version_cli_range"
        )


    elif (
        ans_supports_tf
        and not ans_supports_cli
    ):

        resolution = (
            "secondary_sources_disagree_with_exact_cli"
        )

        status = "resolved"
        confidence = "medium"

        canonical_policy = (
            "prefer_exact_version_cli_range"
        )


    elif (
        ans_ranges
        and not ans_supports_cli
        and not ans_supports_tf
    ):

        resolution = (
            "secondary_sources_disagree_with_exact_cli"
        )

        status = "resolved"
        confidence = "medium"

        canonical_policy = (
            "prefer_exact_version_cli_range"
        )


    elif cli:

        resolution = (
            "exact_version_cli_preferred"
        )

        status = "resolved"
        confidence = "medium"

        canonical_policy = (
            "prefer_exact_version_cli_range"
        )


    else:

        resolution = (
            "cross_source_range_unresolved"
        )

        status = "unresolved"
        confidence = "needs_review"
        canonical_policy = None


    return {

        "resolution":
            resolution,

        "status":
            status,

        "confidence":
            confidence,

        "canonical_policy":
            canonical_policy,

        "special_values":
            special_values,

        "requires_hardware_overlay":
            platform,

        "requires_runtime_validation":
            (
                status == "unresolved"
                or confidence == "medium"
            ),

        "ansible_ranges_detected": [
            [
                number_text(a),
                number_text(b),
            ]
            for a, b
            in ans_ranges
        ],

        "cli_ranges_detected": [
            [
                number_text(a),
                number_text(b),
            ]
            for a, b
            in cli_ranges_detected
        ],

        "cli_units":
            sorted(
                cli_units
            ),

        "ansible_units":
            sorted(
                ans_units
            ),

        "cli_internal_inconsistency":
            cli_internal_inconsistency,
    }


# ============================================================
# MAIN INTEGRATED RESOLVER
# ============================================================

def resolve_semantics(
    root: Path,
    version: str,
    apply: bool = False,
):

    canonical_dir = (
        root
        / "canonical"
    )

    tf_index = build_tf_index(
        root
    )


    type_records = []
    type_counter = Counter()

    range_records = []
    range_counter = Counter()


    canonical_files = list(
        canonical_dir.glob(
            "*.yaml"
        )
    )


    for path in canonical_files:

        section = load_yaml(
            path
        )

        if not isinstance(
            section,
            dict,
        ):
            continue


        sid = (
            section.get("id")
            or path.stem
        )

        attrs = section.get(
            "attributes_flat",
            {},
        )


        # ====================================================
        # TYPES
        # ====================================================

        for conflict in (
            section.get(
                "conflicts"
            )
            or []
        ):

            if (
                conflict.get(
                    "field"
                )
                != "type"
            ):
                continue


            attribute = conflict.get(
                "attribute"
            )

            values = conflict.get(
                "values",
                {},
            )


            classification = (
                classify_type_conflict(
                    values
                )
            )


            result = (
                semantic_type_resolution(
                    classification,
                    values,
                )
            )


            # --------------------------------------------
            # Final Terraform dual representation check
            # --------------------------------------------

            if (
                result.get(
                    "confidence"
                )
                == "needs_review"
            ):

                detected = (
                    detect_dual_tf_representation(
                        tf_index,
                        sid,
                        attribute,
                    )
                )

                if detected:

                    result[
                        "resolution"
                    ] = (
                        "terraform_dual_representation"
                    )

                    result[
                        "confidence"
                    ] = "high"

                    result[
                        "terraform_variants"
                    ] = detected


            type_counter[
                result[
                    "resolution"
                ]
            ] += 1


            record = {
                "section":
                    sid,

                "attribute":
                    attribute,

                "source_types":
                    {
                        src:
                            norm_type(value)

                        for src, value
                        in values.items()
                    },

                "classification":
                    classification,

                **result,
            }


            type_records.append(
                record
            )


            if (
                apply
                and attribute
                in attrs
            ):

                entry = attrs[
                    attribute
                ]

                entry.setdefault(
                    "resolution",
                    {},
                )[
                    "type"
                ] = result


                if result.get(
                    "semantic_type"
                ):

                    entry[
                        "semantic_type"
                    ] = result[
                        "semantic_type"
                    ]


        # ====================================================
        # RANGES
        # ====================================================

        for attribute, entry in (
            attrs.items()
        ):

            if not isinstance(
                entry,
                dict,
            ):
                continue

            evidence = entry.get(
                "evidence",
                {},
            )

            if not isinstance(
                evidence,
                dict,
            ):
                continue


            for field in (
                "min",
                "max",
            ):

                values = {}

                for source, spec in (
                    evidence.items()
                ):

                    if (
                        isinstance(
                            spec,
                            dict,
                        )
                        and field
                        in spec
                        and spec[field]
                        is not None
                    ):

                        values[
                            source
                        ] = spec[
                            field
                        ]


                if len(
                    values
                ) < 2:
                    continue


                normalized = {
                    number_text(value)
                    for value
                    in values.values()
                }


                if len(
                    normalized
                ) <= 1:
                    continue


                result = (
                    resolve_range_record(
                        evidence
                    )
                )


                range_counter[
                    result[
                        "resolution"
                    ]
                ] += 1


                record = {

                    "section":
                        sid,

                    "attribute":
                        attribute,

                    "field":
                        field,

                    "values":
                        values,

                    **result,
                }


                range_records.append(
                    record
                )


                if apply:

                    entry.setdefault(
                        "resolution",
                        {},
                    ).setdefault(
                        "range",
                        {},
                    )[
                        field
                    ] = result


                    if result.get(
                        "special_values"
                    ):

                        entry[
                            "special_values"
                        ] = result[
                            "special_values"
                        ]


                    if result.get(
                        "requires_hardware_overlay"
                    ):

                        entry[
                            "requires_hardware_overlay"
                        ] = True


                    if result.get(
                        "requires_runtime_validation"
                    ):

                        entry[
                            "requires_runtime_validation"
                        ] = True


        if apply:

            dump_yaml(
                path,
                section,
            )


    type_unresolved = sum(
        1
        for item
        in type_records
        if item.get(
            "confidence"
        )
        == "needs_review"
    )


    range_unresolved = sum(
        1
        for item
        in range_records
        if item.get(
            "status"
        )
        == "unresolved"
    )


    report = {

        "version":
            version,

        "apply":
            apply,

        "type_resolution": {

            "total":
                len(
                    type_records
                ),

            "resolved":
                len(
                    type_records
                )
                - type_unresolved,

            "unresolved":
                type_unresolved,

            "summary":
                dict(
                    type_counter
                ),

            "records":
                type_records,
        },

        "range_resolution": {

            "total":
                len(
                    range_records
                ),

            "resolved":
                len(
                    range_records
                )
                - range_unresolved,

            "unresolved":
                range_unresolved,

            "summary":
                dict(
                    range_counter
                ),

            "records":
                range_records,
        },
    }


    dump_yaml(
        root
        / "audit"
        / "semantic_resolution_integrated.yaml",
        report,
    )


    summary = {

        "version":
            version,

        "apply":
            apply,

        "types": {
            "total":
                len(
                    type_records
                ),

            "resolved":
                len(
                    type_records
                )
                - type_unresolved,

            "unresolved":
                type_unresolved,
        },

        "ranges": {
            "total":
                len(
                    range_records
                ),

            "resolved":
                len(
                    range_records
                )
                - range_unresolved,

            "unresolved":
                range_unresolved,
        },
    }


    return summary
