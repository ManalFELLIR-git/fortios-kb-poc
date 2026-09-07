from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
import time

from kb_builder.fortinet_docs import parse_cli_page
from kb_builder.utils import dump_yaml
from kb_builder.reconcile import reconcile_all
from kb_builder.audit import audit


VERSION = "7.6.7"

INDEX = (
    "https://docs.fortinet.com/document/"
    "fortigate/7.6.7/cli-reference/"
    "84566/fortios-cli-reference"
)

ROOT = Path("knowledge_base/fortios/7.6.7")
OUT = ROOT / "raw" / "docs" / "cli_reference"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


print("=== 1. Lecture index Fortinet ===")

r = requests.get(
    INDEX,
    headers=HEADERS,
    timeout=30
)

r.raise_for_status()

soup = BeautifulSoup(
    r.text,
    "html.parser"
)


urls = {}

for a in soup.find_all("a", href=True):

    text = " ".join(
        a.get_text(
            " ",
            strip=True
        ).split()
    )

    url = urljoin(
        INDEX,
        a["href"]
    ).split("#", 1)[0]

    slug = (
        url.rstrip("/")
        .split("/")[-1]
        .lower()
    )

    if (
        text.lower().startswith("config ")
        or slug.startswith("config-")
    ):

        urls[url] = text


urls = sorted(urls.keys())

print(
    f"[OK] {len(urls)} pages CONFIG trouvées"
)


manifest = ROOT / "raw" / "docs" / "cli_urls.txt"

manifest.parent.mkdir(
    parents=True,
    exist_ok=True
)

manifest.write_text(
    "\n".join(urls),
    encoding="utf-8"
)

print(
    f"[OK] Liste sauvegardée : {manifest}"
)


print()
print("=== 2. Nettoyage ancienne CLI partielle ===")

if OUT.exists():

    for file in OUT.glob("*.yaml"):
        file.unlink()

OUT.mkdir(
    parents=True,
    exist_ok=True
)

print("[OK] CLI raw nettoyée")


print()
print("=== 3. Scraping ciblé CONFIG uniquement ===")

success = 0
failed = []

total = len(urls)

for i, url in enumerate(
    urls,
    start=1
):

    print(
        f"[CLI] {i}/{total} {url}",
        flush=True
    )

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        item = parse_cli_page(
            r.text,
            url,
            VERSION
        )

        if not item:

            print(
                "     [SKIP] page non reconnue"
            )

            failed.append({
                "url": url,
                "reason": "parse_none"
            })

            continue

        dump_yaml(
            OUT / f"{item['id']}.yaml",
            item
        )

        success += 1

    except Exception as exc:

        print(
            f"     [ERROR] {exc}"
        )

        failed.append({
            "url": url,
            "reason": repr(exc)
        })

    time.sleep(0.05)


print()
print("=== 4. Reconciliation ===")

reconcile_all(
    ROOT,
    VERSION
)


print()
print("=== 5. Audit ===")

report = audit(
    ROOT,
    VERSION,
    failed
)


print()
print("============================")
print("RESULTAT SCRAPING CLI")
print("============================")

print(
    "URLs config trouvées :",
    total
)

print(
    "Pages parsées        :",
    success
)

print(
    "Échecs               :",
    len(failed)
)

print()

for key, value in report.items():
    print(
        f"{key}: {value}"
    )
