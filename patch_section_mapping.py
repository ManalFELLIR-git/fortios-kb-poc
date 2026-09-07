from pathlib import Path
import re
import shutil

path = Path("kb_builder/reconcile.py")

backup = Path(
    "kb_builder/reconcile.py.before_section_mapping.bak"
)

if not backup.exists():
    shutil.copy2(path, backup)


def replace_function(text, name, new_code):
    start = text.find(f"def {name}(")

    if start == -1:
        raise RuntimeError(
            f"Fonction introuvable : {name}"
        )

    rest = text[start + 1:]

    match = re.search(
        r"\n(?=def [A-Za-z_][A-Za-z0-9_]*\()",
        rest
    )

    if match:
        end = start + 1 + match.start()

        return (
            text[:start]
            + new_code.rstrip()
            + "\n\n"
            + text[end + 1:]
        )

    return (
        text[:start]
        + new_code.rstrip()
        + "\n"
    )


text = path.read_text(
    encoding="utf-8"
)

# reconcile.py aura besoin de re
if "import re" not in text:
    text = text.replace(
        "from pathlib import Path",
        "from pathlib import Path\nimport re",
        1
    )


# =========================================================
# CLE GENERIQUE DE MATCHING DES SECTIONS
# =========================================================

section_match_key_code = r'''
def section_match_key(section_id: str) -> str:
    """
    Crée une clé de comparaison indépendante de la forme.

    Exemples:

    application.classification-settings
    application.classificationsettings
        -> applicationclassificationsettings

    firewall.DoS-policy
    firewall.dos-policy
    firewall.dospolicy
        -> firewalldospolicy
    """

    return re.sub(
        r"[^a-z0-9]",
        "",
        (section_id or "").lower()
    )
'''


build_index_code = r'''
def build_unique_section_index(source_map):
    """
    Construit:
        clé normalisée -> ID canonique

    Seulement lorsque la clé correspond à un ID unique.

    En cas d'ambiguïté, aucun mapping automatique.
    """

    buckets = {}

    for section_id in source_map:

        key = section_match_key(
            section_id
        )

        buckets.setdefault(
            key,
            []
        ).append(
            section_id
        )

    unique = {}

    ambiguous = {}

    for key, ids in buckets.items():

        ids = sorted(
            set(ids)
        )

        if len(ids) == 1:
            unique[key] = ids[0]

        else:
            ambiguous[key] = ids

    return unique, ambiguous
'''


remap_code = r'''
def remap_source_sections(
    source_map,
    authority_index,
    source_name
):
    """
    Mappe une source vers les IDs de l'autorité
    (CLI d'abord, puis bridge Ansible).

    Aucune donnée brute n'est modifiée.
    """

    mapped = {}
    aliases = []
    collisions = []

    for raw_id, item in sorted(
        source_map.items()
    ):

        raw_lower = raw_id.lower()

        key = section_match_key(
            raw_id
        )

        canonical_id = authority_index.get(
            key,
            raw_lower
        )

        # Ne jamais écraser silencieusement
        # deux objets différents.
        if canonical_id in mapped:

            collisions.append({
                "source": source_name,
                "canonical_id": canonical_id,
                "existing_source_id":
                    mapped[canonical_id].get(
                        "source_section_id",
                        mapped[canonical_id].get("id")
                    ),
                "new_source_id": raw_id,
            })

            # conserver la deuxième ressource
            # sous son ID original plutôt
            # que perdre de l'information.
            canonical_id = raw_lower

        new_item = dict(
            item
        )

        new_item[
            "source_section_id"
        ] = raw_id

        new_item[
            "id"
        ] = canonical_id

        mapped[
            canonical_id
        ] = new_item

        if raw_id != canonical_id:

            aliases.append({
                "from": raw_id,
                "to": canonical_id,
                "match_key": key,
            })

    return mapped, aliases, collisions
'''


helpers = [
    (
        "section_match_key",
        section_match_key_code
    ),
    (
        "build_unique_section_index",
        build_index_code
    ),
    (
        "remap_source_sections",
        remap_code
    ),
]


for name, code in helpers:

    if f"def {name}(" in text:

        text = replace_function(
            text,
            name,
            code
        )

    else:

        marker = "def reconcile_all("

        if marker not in text:
            raise RuntimeError(
                "reconcile_all introuvable"
            )

        text = text.replace(
            marker,
            code.rstrip()
            + "\n\n\n"
            + marker,
            1
        )


# =========================================================
# NOUVELLE RECONCILIATION DES SECTIONS
# =========================================================

new_reconcile_all = r'''
def reconcile_all(root: Path, version: str):

    # -----------------------------------------------------
    # 1. Charger les sources RAW
    # -----------------------------------------------------

    a_raw = load_sections(
        root / "raw" / "ansible"
    )

    t_raw = load_sections(
        root / "raw" / "terraform"
    )

    c_raw = load_sections(
        root
        / "raw"
        / "docs"
        / "cli_reference"
    )


    # -----------------------------------------------------
    # 2. CLI = autorité de nommage
    # -----------------------------------------------------

    c, cli_aliases, cli_collisions = (
        remap_source_sections(
            c_raw,
            {},
            "cli_reference"
        )
    )

    cli_index, cli_ambiguous = (
        build_unique_section_index(c)
    )


    # -----------------------------------------------------
    # 3. ANSIBLE -> CLI
    # -----------------------------------------------------

    a, ansible_aliases, ansible_collisions = (
        remap_source_sections(
            a_raw,
            cli_index,
            "ansible"
        )
    )


    # -----------------------------------------------------
    # 4. Construire une autorité élargie
    #
    # CLI
    #  +
    # Ansible déjà aligné CLI
    #
    # Cela permet aussi à Terraform de matcher
    # des sections non présentes dans la CLI.
    # -----------------------------------------------------

    authority = {}

    for sid in c:
        authority[sid] = c[sid]

    for sid in a:
        authority.setdefault(
            sid,
            a[sid]
        )

    authority_index, authority_ambiguous = (
        build_unique_section_index(
            authority
        )
    )


    # -----------------------------------------------------
    # 5. TERRAFORM -> CLI / ANSIBLE
    # -----------------------------------------------------

    t, terraform_aliases, terraform_collisions = (
        remap_source_sections(
            t_raw,
            authority_index,
            "terraform"
        )
    )


    # -----------------------------------------------------
    # 6. Reconstruire complètement CANONICAL
    # -----------------------------------------------------

    canonical_dir = (
        root / "canonical"
    )

    canonical_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # supprimer les anciens fichiers
    # pour éviter les IDs obsolètes
    for old in canonical_dir.glob(
        "*.yaml"
    ):
        old.unlink()


    ids = sorted(
        set(a)
        | set(t)
        | set(c)
    )

    merged = []

    for sid in ids:

        item = reconcile_section(
            sid,
            a.get(sid),
            t.get(sid),
            c.get(sid),
            version
        )

        dump_yaml(
            canonical_dir
            / f"{sid}.yaml",
            item
        )

        merged.append(
            item
        )


    # -----------------------------------------------------
    # 7. Rapport de mapping
    # -----------------------------------------------------

    mapping_report = {

        "version": version,

        "strategy": (
            "CLI unique normalized key, "
            "then Ansible bridge, "
            "no guessing on ambiguity"
        ),

        "raw_counts": {
            "ansible": len(a_raw),
            "terraform": len(t_raw),
            "cli_reference": len(c_raw),
        },

        "mapped_counts": {
            "ansible": len(a),
            "terraform": len(t),
            "cli_reference": len(c),
        },

        "alias_counts": {
            "ansible": len(ansible_aliases),
            "terraform": len(terraform_aliases),
            "cli_reference": len(cli_aliases),
        },

        "aliases": {
            "ansible": ansible_aliases,
            "terraform": terraform_aliases,
            "cli_reference": cli_aliases,
        },

        "ambiguities": {
            "cli_reference":
                cli_ambiguous,

            "authority":
                authority_ambiguous,
        },

        "collisions": {
            "ansible":
                ansible_collisions,

            "terraform":
                terraform_collisions,

            "cli_reference":
                cli_collisions,
        },
    }

    dump_yaml(
        root
        / "audit"
        / "section_mapping.yaml",
        mapping_report
    )

    return merged
'''


text = replace_function(
    text,
    "reconcile_all",
    new_reconcile_all
)


path.write_text(
    text,
    encoding="utf-8"
)

print()
print(
    "[OK] Mapping générique des sections installé"
)

print(
    "[OK] CLI = autorité de nommage"
)

print(
    "[OK] Ansible = bridge secondaire"
)

print(
    "[OK] Aucun mapping manuel"
)

print(
    "[OK] Ambiguïtés conservées pour audit"
)

print(
    "[BACKUP]",
    backup
)
