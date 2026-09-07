import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url = "https://docs.fortinet.com/document/fortigate/7.6.7/cli-reference/84566/fortios-cli-reference"

html = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    },
    timeout=30
).text

soup = BeautifulSoup(
    html,
    "html.parser"
)

found = []

for a in soup.find_all("a", href=True):

    href = urljoin(
        url,
        a["href"]
    )

    text = " ".join(
        a.get_text(
            " ",
            strip=True
        ).split()
    )

    combined = (
        text
        + " "
        + href
    ).lower()

    if (
        "system-sdwan" in combined
        or "system sdwan" in combined
    ):
        found.append(
            (
                text,
                href
            )
        )

for text, href in found:
    print(text)
    print(href)
    print()

print(
    "RESULTATS:",
    len(found)
)
