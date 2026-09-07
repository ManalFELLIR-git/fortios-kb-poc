from __future__ import annotations
from pathlib import Path
import re
from .utils import load_yaml, dump_yaml, flatten_attributes, canonical_type


def load_sections(folder: Path):
    out = {}
    if not folder.exists(): return out
    for p in folder.glob("*.yaml"):
        try:
            d = load_yaml(p)
            if d and d.get("id"): out[d["id"]] = d
        except Exception:
            pass
    return out



def normalize_attr_path(path: str) -> str:
    """
    FortiOS CLI:
        duplication-max-num

    Ansible / Terraform:
        duplication_max_num

    Forme canonique interne:
        duplication_max_num
    """
    return ".".join(
        part.replace("-", "_")
        for part in path.split(".")
    )



def attr_map(section):
    if not section:
        return {}

    result = {}

    for path, spec in flatten_attributes(section):

        canonical_path = normalize_attr_path(
            path
        )

        spec = dict(spec or {})

        # Conserver le nom original.
        spec.setdefault(
            "source_attribute",
            path
        )

        result[canonical_path] = spec

    return result

def sig(spec):
    if not spec: return None
    choices = spec.get("choices")
    return {
        "type": canonical_type(spec.get("type") or spec.get("raw_type"), choices),
        "choices": tuple(choices or []),
        "default": spec.get("default"),
        "min": spec.get("min"), "max": spec.get("max"),
        "min_length": spec.get("min_length"), "max_length": spec.get("max_length"),
    }




def choose_type(per):
    """
    Choisit le type canonique sans laisser une représentation CLI
    plate écraser une structure list/dict connue par Ansible/Terraform.
    """

    # Une structure explicite list/dict avec enfants a priorité.
    for src in ["ansible", "terraform", "cli_reference"]:
        spec = per.get(src)

        if not spec:
            continue

        stype = canonical_type(
            spec.get("type") or spec.get("raw_type"),
            spec.get("choices")
        )

        if (
            stype in {"list", "dict"}
            and (
                spec.get("children")
                or spec.get("elements")
            )
        ):
            return stype, src

    # Sinon CLI officielle en premier.
    for src in ["cli_reference", "ansible", "terraform"]:
        spec = per.get(src)

        if not spec:
            continue

        stype = canonical_type(
            spec.get("type") or spec.get("raw_type"),
            spec.get("choices")
        )

        if stype:
            # enum est plus précis que string si des choices existent
            if (
                stype == "string"
                and spec.get("choices")
            ):
                return "enum", src

            return stype, src

    return None, None


def first_value(per, field, order):
    for src in order:
        spec = per.get(src)

        if (
            spec
            and field in spec
            and spec[field] is not None
        ):
            return spec[field], src

    return None, None


def build_canonical(per):
    """
    Fusion champ par champ.

    CLI Reference:
      description/default/range/choices

    Ansible/Terraform:
      structure/list/children/references/version
    """

    canonical = {}
    field_sources = {}

    chosen_type, type_src = choose_type(per)

    if chosen_type:
        canonical["type"] = chosen_type
        field_sources["type"] = type_src

    # Structure : priorité aux sources structurées
    for field in [
        "elements",
        "children",
        "references",
        "required",
        "version_ranges",
    ]:
        value, src = first_value(
            per,
            field,
            ["ansible", "terraform", "cli_reference"]
        )

        if value is not None:
            canonical[field] = value
            field_sources[field] = src

    # Vérité documentaire officielle
    for field in [
        "choices",
        "default",
        "min",
        "max",
        "min_length",
        "max_length",
        "description",
    ]:
        value, src = first_value(
            per,
            field,
            ["cli_reference", "ansible", "terraform"]
        )

        if value is not None:
            canonical[field] = value
            field_sources[field] = src

    # Nom CLI original si disponible
    value, src = first_value(
        per,
        "source_attribute",
        ["cli_reference", "ansible", "terraform"]
    )

    if value is not None:
        canonical["source_attribute"] = value
        field_sources["source_attribute"] = src

    return canonical, field_sources



def reconcile_section(sid, a, t, c, version):
    maps = {
        "ansible": attr_map(a),
        "terraform": attr_map(t),
        "cli_reference": attr_map(c),
    }

    all_attrs = sorted(
        set().union(
            *(m.keys() for m in maps.values())
        )
    )

    attrs = {}
    conflicts = []

    for ap in all_attrs:

        per = {
            src: m.get(ap)
            for src, m in maps.items()
            if m.get(ap) is not None
        }

        signatures = {
            src: sig(value)
            for src, value in per.items()
        }

        types = {
            src: signature["type"]
            for src, signature in signatures.items()
            if signature and signature.get("type")
        }

        norm_types = set(types.values())

        # enum/string = différence de représentation acceptable.
        compatible = (
            norm_types <= {"string", "enum"}
            or len(norm_types) <= 1
        )

        if not compatible:
            conflicts.append({
                "attribute": ap,
                "field": "type",
                "values": types,
                "classification": "representation_or_real_conflict",
            })

        canonical, field_sources = build_canonical(per)

        attrs[ap] = {
            "canonical": canonical,
            "canonical_source": "merged",
            "field_sources": field_sources,
            "evidence": per,
            "sources": sorted(per.keys()),
        }

    return {
        "id": sid,
        "version": version,

        "source_presence": {
            "ansible": bool(a),
            "terraform": bool(t),
            "cli_reference": bool(c),
        },

        "attributes_flat": attrs,
        "conflicts": conflicts,
    }


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




def terraform_resource_name(section_id: str) -> str:
    """
    Convertit l'ID RAW Terraform vers le nom du resource provider.

    Exemples:
      firewall.security_policy
        -> fortios_firewall_security_policy

      vpnipsec.phase1interface
        -> fortios_vpnipsec_phase1interface
    """

    return (
        "fortios_"
        + str(section_id).replace(".", "_")
    )


def discover_terraform_deprecations(
    terraform_map,
    repo_root=Path(".work/terraform")
):
    """
    Détecte automatiquement les resources Terraform legacy
    à partir de la documentation du provider.

    Aucune règle FortiOS/version n'est hardcodée.
    """

    docs_root = (
        repo_root
        / "website"
        / "docs"
        / "r"
    )

    result = {}

    if not docs_root.exists():
        return result

    resource_to_section = {
        terraform_resource_name(sid): sid
        for sid in terraform_map
    }

    pattern = re.compile(
        r"replaced\s+by\s+new\s+resource"
        r"\s+[`'\"]"
        r"(fortios_[A-Za-z0-9_]+)"
        r"[`'\"]",
        re.IGNORECASE
    )

    for sid in terraform_map:

        resource = terraform_resource_name(
            sid
        )

        doc = (
            docs_root
            / f"{resource}.html.markdown"
        )

        if not doc.exists():
            continue

        try:
            content = doc.read_text(
                encoding="utf-8",
                errors="ignore"
            )
        except Exception:
            continue

        match = pattern.search(
            content
        )

        if not match:
            continue

        replacement_resource = (
            match.group(1)
        )

        replacement_sid = (
            resource_to_section.get(
                replacement_resource
            )
        )

        # On ne retire le legacy que si
        # le remplacement existe réellement
        # dans cette release du provider.
        if replacement_sid:

            result[sid] = {
                "legacy_resource":
                    resource,

                "legacy_section_id":
                    sid,

                "replacement_resource":
                    replacement_resource,

                "replacement_section_id":
                    replacement_sid,

                "documentation":
                    str(doc),
            }

    return result


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
    # 5. Détecter les anciens resources Terraform
    #
    # Ils restent dans RAW pour la provenance,
    # mais ne participent pas à la vérité canonique
    # lorsqu'un remplacement officiel existe.
    # -----------------------------------------------------

    terraform_deprecations = (
        discover_terraform_deprecations(
            t_raw
        )
    )

    deprecated_terraform_ids = set(
        terraform_deprecations
    )

    t_primary_raw = {
        sid: item
        for sid, item in t_raw.items()
        if sid not in deprecated_terraform_ids
    }

    dump_yaml(
        root
        / "audit"
        / "terraform_deprecations.yaml",
        {
            "version": version,
            "deprecated_count":
                len(terraform_deprecations),
            "resources":
                terraform_deprecations,
        }
    )


    # -----------------------------------------------------
    # 6. TERRAFORM ACTIF -> CLI / ANSIBLE
    # -----------------------------------------------------

    t, terraform_aliases, terraform_collisions = (
        remap_source_sections(
            t_primary_raw,
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
