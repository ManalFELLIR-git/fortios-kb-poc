from pathlib import Path
import shutil

path = Path("resolve_range_conflicts.py")

backup = Path(
    "resolve_range_conflicts.py.before_v2.bak"
)

if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(
    encoding="utf-8"
)


# ============================================================
# 1. Remplacer simple_ranges()
#    Supporte maintenant :
#
#      20 - 3600 * 1000
#
# ============================================================

start = text.index(
    "def simple_ranges(text):"
)

end = text.index(
    "\ndef description_supports_range",
    start
)

new_function = r'''def simple_ranges(text):
    """
    Récupère des ranges textuels simples :

        1 - 10
        12 to 128
        0 – 65535
        20 - 3600 * 1000

    Les expressions restent volontairement limitées
    à une multiplication numérique simple.
    """

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

    for m in pattern.finditer(
        str(text)
    ):

        a = number(
            m.group(1)
        )

        b = number(
            m.group(2)
        )

        multiplier = number(
            m.group(3)
        ) if m.group(3) else None

        if (
            b is not None
            and multiplier is not None
        ):
            b = b * multiplier

        if (
            a is not None
            and b is not None
        ):
            result.append(
                (a, b)
            )

    return result
'''

text = (
    text[:start]
    + new_function
    + text[end:]
)


# ============================================================
# 2. Ajouter détection de contradiction interne CLI
# ============================================================

needle = '''    default_outside_range = False

    if (
        cli_default is not None
        and mn is not None
        and mx is not None
    ):

        default_outside_range = (
            cli_default < mn
            or cli_default > mx
        )
'''

replacement = '''    default_outside_range = False

    if (
        cli_default is not None
        and mn is not None
        and mx is not None
    ):

        default_outside_range = (
            cli_default < mn
            or cli_default > mx
        )


    # --------------------------------------------------------
    # Vérifier si la description CLI contredit elle-même
    # les champs structurés min/max.
    #
    # Exemple :
    #
    # description : 10 - 3600
    # min structuré: 180
    # max structuré: 3600
    #
    # Dans ce cas on ne tranche pas automatiquement.
    # --------------------------------------------------------

    cli_ranges_detected = simple_ranges(
        cli_desc
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
        bool(cli_ranges_detected)
        and cli_structured_range is not None
        and cli_structured_range
        not in cli_ranges_detected
    )
'''

if needle not in text:
    raise RuntimeError(
        "Bloc default_outside_range introuvable"
    )

text = text.replace(
    needle,
    replacement,
    1
)


# ============================================================
# 3. Ajouter RULE 0 avant platform dependency
# ============================================================

needle = '''    # ========================================================
    # RULE 1 — dépendance hardware / plateforme explicite
    # ========================================================

    if platform:
'''

replacement = '''    # ========================================================
    # RULE 0 — contradiction interne dans la source officielle
    #
    # Ne jamais choisir automatiquement lorsque la CLI
    # structurée et sa propre description ne sont pas
    # cohérentes.
    # ========================================================

    if cli_internal_inconsistency:

        resolution = (
            "official_cli_internal_inconsistency"
        )

        status = "unresolved"

        confidence = "needs_review"

        canonical_policy = None


    # ========================================================
    # RULE 1 — dépendance hardware / plateforme explicite
    # ========================================================

    elif platform:
'''

if needle not in text:
    raise RuntimeError(
        "RULE 1 introuvable"
    )

text = text.replace(
    needle,
    replacement,
    1
)


# ============================================================
# 4. Modifier RULE 4
#
# Si Ansible + Terraform sont d'accord mais diffèrent de
# la CLI exacte, on garde CLI pour cette version et les
# autres comme evidence.
# ============================================================

old_rule4 = '''    elif (
        ans_supports_tf
        and not ans_supports_cli
    ):

        resolution = (
            "cross_source_disagreement"
        )

        status = "unresolved"

        confidence = "needs_review"

        canonical_policy = None
'''

new_rule4 = '''    elif (
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
'''

if old_rule4 not in text:
    raise RuntimeError(
        "RULE 4 introuvable"
    )

text = text.replace(
    old_rule4,
    new_rule4,
    1
)


# ============================================================
# 5. Modifier RULE 6
#
# Même principe lorsqu'Ansible fournit une troisième valeur :
# si la CLI exacte est cohérente avec elle-même, elle reste
# la contrainte canonique de cette version.
# ============================================================

old_rule6 = '''    elif (
        ans_ranges
        and not ans_supports_cli
        and not ans_supports_tf
    ):

        resolution = (
            "three_way_range_disagreement"
        )

        status = "unresolved"

        confidence = "needs_review"

        canonical_policy = None
'''

new_rule6 = '''    elif (
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
'''

if old_rule6 not in text:
    raise RuntimeError(
        "RULE 6 introuvable"
    )

text = text.replace(
    old_rule6,
    new_rule6,
    1
)


# ============================================================
# 6. Ajouter informations audit dans le résultat
# ============================================================

needle = '''        "requires_hardware_overlay":
            platform,
    })
'''

replacement = '''        "requires_hardware_overlay":
            platform,

        "cli_ranges_detected": [
            [
                number_text(a),
                number_text(b),
            ]
            for a, b
            in cli_ranges_detected
        ],

        "cli_internal_inconsistency":
            cli_internal_inconsistency,

        "requires_runtime_validation":
            (
                status == "unresolved"
                or confidence == "medium"
            ),
    })
'''

if needle not in text:
    raise RuntimeError(
        "Bloc result.update introuvable"
    )

text = text.replace(
    needle,
    replacement,
    1
)


path.write_text(
    text,
    encoding="utf-8"
)

print()
print(
    "[OK] resolve_range_conflicts.py patché V2"
)

print(
    "[OK] arithmetic ranges supportés"
)

print(
    "[OK] contradiction interne CLI détectée"
)

print(
    "[OK] exact-version CLI authority ajoutée"
)

print(
    "[BACKUP]",
    backup
)
