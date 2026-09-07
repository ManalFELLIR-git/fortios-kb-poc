from pathlib import Path
import shutil

path = Path("kb_builder/fortinet_docs.py")
backup = Path("kb_builder/fortinet_docs.py.before_targeted_cli.bak")

if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(
    encoding="utf-8"
)


# ============================================================
# 1. Ajouter le discovery ciblé CLI
# ============================================================

marker = "\ndef crawl(seed: str, allowed_prefixes: list[str], max_pages: int, delay: float=0.15):"

if marker not in text:
    raise RuntimeError(
        "Point d'insertion crawl() introuvable"
    )


new_code = r'''

def discover_cli_config_links(
    html: str,
    base_url: str,
    version: str,
):
    """
    Découvre uniquement les vraies pages FortiOS:

        config ...

    depuis l'index CLI Reference.

    Aucun crawl récursif vers:
        diagnose
        execute
        get
        tree/category pages

    La logique est indépendante de la version.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    prefix = (
        f"https://docs.fortinet.com/"
        f"document/fortigate/{version}/"
        f"cli-reference/"
    )

    links = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        url = urljoin(
            base_url,
            a["href"]
        )

        url = (
            url
            .split("#", 1)[0]
            .split("?", 1)[0]
        )

        if not url.startswith(
            prefix
        ):
            continue

        anchor_text = clean_text(
            a.get_text(" ")
        ).lower()

        slug = (
            urlparse(url)
            .path
            .rstrip("/")
            .split("/")[-1]
            .lower()
        )

        if (
            anchor_text.startswith(
                "config "
            )
            or slug.startswith(
                "config-"
            )
        ):
            links.add(
                url
            )

    return sorted(
        links
    )


def build_cli_reference(
    version: str,
    seed: str,
    out_dir: Path,
    delay: float = 0.15,
):
    """
    Construit la couche CLI Reference complète
    avec collecte ciblée des pages config.

    Le dossier CLI est reconstruit proprement afin
    qu'aucune ancienne page ne survive à un nouveau run.
    """

    errors = []

    target_dir = (
        out_dir
        / "cli_reference"
    )

    target_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------------
    # Nettoyage atomique logique de l'ancien RAW CLI.
    # On ne mélange jamais un ancien crawl avec le nouveau.
    # --------------------------------------------------------

    for old in target_dir.glob(
        "*.yaml"
    ):
        old.unlink()


    try:

        seed_html = fetch(
            seed
        )

    except Exception as exc:

        errors.append({
            "url": seed,
            "error": repr(exc),
            "stage": "cli_index",
        })

        return {
            "cli_reference_discovered": 0,
            "cli_reference_sections": 0,
            "cli_reference_failed": 1,
        }, errors


    urls = discover_cli_config_links(
        seed_html,
        seed,
        version,
    )


    print(
        f"[CLI] config pages discovered: "
        f"{len(urls)}",
        flush=True
    )


    manifest = []

    seen_ids = {}

    parsed_count = 0


    for index, url in enumerate(
        urls,
        start=1
    ):

        print(
            f"[CLI] "
            f"{index}/{len(urls)} "
            f"{url}",
            flush=True
        )


        try:

            html = fetch(
                url
            )

            item = parse_cli_page(
                html,
                url,
                version,
            )


            if not item:

                error = {
                    "url": url,
                    "error":
                        "page_discovered_as_config_"
                        "but_parser_returned_none",
                    "stage": "cli_parse",
                }

                errors.append(
                    error
                )

                manifest.append({
                    "url": url,
                    "status": "parse_failed",
                })

                continue


            section_id = item[
                "id"
            ]


            # Ne jamais écraser silencieusement
            # deux URLs qui produisent le même ID.
            if section_id in seen_ids:

                error = {
                    "url": url,
                    "error":
                        "duplicate_section_id",
                    "section_id":
                        section_id,
                    "first_url":
                        seen_ids[
                            section_id
                        ],
                    "stage":
                        "cli_duplicate",
                }

                errors.append(
                    error
                )

                manifest.append({
                    "url":
                        url,
                    "status":
                        "duplicate",
                    "section_id":
                        section_id,
                })

                continue


            seen_ids[
                section_id
            ] = url


            dump_yaml(
                target_dir
                / f"{section_id}.yaml",
                item,
            )


            parsed_count += 1


            manifest.append({
                "url":
                    url,
                "status":
                    "parsed",
                "section_id":
                    section_id,
            })


        except Exception as exc:

            errors.append({
                "url":
                    url,
                "error":
                    repr(exc),
                "stage":
                    "cli_fetch_or_parse",
            })

            manifest.append({
                "url":
                    url,
                "status":
                    "error",
                "error":
                    repr(exc),
            })


        if delay:
            time.sleep(
                delay
            )


    # --------------------------------------------------------
    # Manifest de provenance
    # --------------------------------------------------------

    dump_yaml(
        out_dir
        / "manifests"
        / "cli_reference.yaml",
        {
            "version":
                version,

            "seed":
                seed,

            "discovered":
                len(urls),

            "parsed":
                parsed_count,

            "failed":
                len(errors),

            "pages":
                manifest,
        }
    )


    stats = {

        "cli_reference_discovered":
            len(urls),

        "cli_reference_sections":
            parsed_count,

        "cli_reference_failed":
            len(errors),
    }


    return (
        stats,
        errors
    )

'''

text = text.replace(
    marker,
    new_code + marker,
    1
)


# ============================================================
# 2. Remplacer l'ancien crawl CLI dans build_docs()
# ============================================================

start_marker = '''    # CLI
'''

end_marker = '''    # Admin Guide
'''

start = text.index(
    start_marker,
    text.index("def build_docs")
)

end = text.index(
    end_marker,
    start
)


replacement = '''    # --------------------------------------------------
    # CLI Reference
    #
    # Collection ciblée:
    # uniquement les pages "config ..."
    # --------------------------------------------------

    cli_stats, cli_errors = (
        build_cli_reference(
            version,
            seeds["cli_reference"],
            out_dir,
        )
    )

    stats.update(
        cli_stats
    )

    errors.extend(
        cli_errors
    )

'''


text = (
    text[:start]
    + replacement
    + text[end:]
)


path.write_text(
    text,
    encoding="utf-8"
)


print()
print(
    "[OK] fortinet_docs.py patché"
)

print(
    "[OK] CLI recursive crawl supprimé"
)

print(
    "[OK] discovery ciblée config ajoutée"
)

print(
    "[OK] manifest CLI ajouté"
)

print(
    "[OK] protection duplicate section ID"
)

print(
    "[OK] ancien RAW CLI nettoyé avant rebuild"
)

print(
    "[BACKUP]",
    backup
)
