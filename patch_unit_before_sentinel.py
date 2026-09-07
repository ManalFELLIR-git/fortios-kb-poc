from pathlib import Path
import shutil
import re

path = Path("resolve_range_conflicts.py")

backup = Path(
    "resolve_range_conflicts.py.before_unit_vs_sentinel_fix.bak"
)

if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(
    encoding="utf-8"
)


def rule_start(number, text_value):

    m = re.search(
        rf"(?m)^    # RULE {number} — {re.escape(text_value)}.*$",
        text
    )

    if not m:
        raise RuntimeError(
            f"RULE {number} introuvable: {text_value}"
        )

    start = text.rfind(
        "    # ========================================================",
        0,
        m.start()
    )

    return start


# Ordre actuel :
# RULE 2 = sentinel
# RULE 3 = units
# RULE 4 = Ansible -> CLI

p2 = rule_start(
    2,
    "valeur sentinelle explicite"
)

p3 = rule_start(
    3,
    "unités différentes"
)

p4 = rule_start(
    4,
    "Ansible confirme exactement la CLI"
)


if not (
    p2 < p3 < p4
):
    raise RuntimeError(
        "Ordre inattendu. Aucun changement effectué."
    )


sentinel_block = text[p2:p3]
unit_block = text[p3:p4]


# Renuméroter les commentaires
unit_block = unit_block.replace(
    "# RULE 3 —",
    "# RULE 2 —",
    1
)

sentinel_block = sentinel_block.replace(
    "# RULE 2 —",
    "# RULE 3 —",
    1
)


new_text = (
    text[:p2]
    + unit_block
    + sentinel_block
    + text[p4:]
)


path.write_text(
    new_text,
    encoding="utf-8"
)


print("[OK] unit_mismatch passe avant sentinel")
print("[OK] RULE 2 = unités différentes")
print("[OK] RULE 3 = valeur sentinelle")
print("[BACKUP]", backup)
