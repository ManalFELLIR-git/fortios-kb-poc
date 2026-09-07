from pathlib import Path
import shutil

path = Path("resolve_range_conflicts.py")
backup = Path("resolve_range_conflicts.py.before_unit_order_fix.bak")

if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(encoding="utf-8")

old = '''    # ========================================================
    # RULE 3 — Ansible confirme exactement la CLI
    # ========================================================

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


    # ========================================================
    # RULE 4 — Ansible confirme Terraform au lieu deCLI
    # ========================================================

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


    # ========================================================
    # RULE 5 — unités différentes
    # ========================================================

    elif unit_mismatch:

        resolution = (
            "unit_or_semantic_disagreement"
        )

        status = "unresolved"

        confidence = "needs_review"

        canonical_policy = None
'''

new = '''    # ========================================================
    # RULE 3 — unités différentes
    #
    # Cette règle passe avant les comparaisons numériques.
    # Deux valeurs identiques ne sont pas équivalentes si
    # elles utilisent des unités différentes.
    # ========================================================

    elif unit_mismatch:

        resolution = (
            "unit_or_semantic_disagreement"
        )

        status = "unresolved"

        confidence = "needs_review"

        canonical_policy = None


    # ========================================================
    # RULE 4 — Ansible confirme exactement la CLI
    # ========================================================

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


    # ========================================================
    # RULE 5 — Ansible confirme Terraform au lieu de CLI
    # ========================================================

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
'''

if old not in text:
    raise RuntimeError(
        "Bloc attendu introuvable. Aucun changement effectué."
    )

text = text.replace(old, new, 1)

path.write_text(
    text,
    encoding="utf-8"
)

print("[OK] Ordre des règles corrigé")
print("[OK] unit_mismatch passe avant les comparaisons de ranges")
print("[BACKUP]", backup)
