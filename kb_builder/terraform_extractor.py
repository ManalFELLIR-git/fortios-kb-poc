from __future__ import annotations
from pathlib import Path
import re
import ast
from .utils import canonical_type, dump_yaml


def matching_brace(text: str, open_pos: int, open_ch="{", close_ch="}"):
    depth = 0
    in_str = False
    esc = False
    for i in range(open_pos, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1


def find_schema_map(text: str):
    m = re.search(r"\bSchema\s*:\s*map\[string\]\*schema\.Schema\s*\{", text)
    if not m:
        return None
    op = text.find("{", m.start())
    end = matching_brace(text, op)
    return text[op+1:end] if end > op else None


def top_level_entries(block: str):
    entries = []
    i = 0
    while i < len(block):
        m = re.search(r'"([^"\\]+)"\s*:\s*&schema\.Schema\s*\{', block[i:])
        if not m:
            break
        name = m.group(1)
        start = i + m.end() - 1
        end = matching_brace(block, start)
        if end < 0:
            break
        entries.append((name, block[start+1:end]))
        i = end + 1
    return entries



def _protect_inline_slice_literals(text: str):
    """
    Protège les littéraux Go :

        []string{"a", "b"}
        []int{1, 2}

    avant direct_level_text().

    Le but est de conserver les valeurs utilisées par
    validation.StringInSlice / IntInSlice sans réintroduire
    les contraintes appartenant aux schemas enfants.
    """

    protected = {}

    pattern = re.compile(
        r"\[\]\s*(?:string|int)\s*\{[^{}]*\}",
        re.S,
    )

    def repl(match):
        token = (
            f"__FORTIOS_SLICE_LITERAL_"
            f"{len(protected)}__"
        )

        protected[token] = match.group(0)

        return token

    return (
        pattern.sub(repl, text),
        protected,
    )


def direct_level_text(body: str) -> str:
    """
    Garde uniquement les propriétés du niveau courant.

    Les blocs enfants Terraform sont masqués afin qu'un
    parent ne récupère jamais les validations de ses enfants.

    Les littéraux []string{...} / []int{...} du niveau
    courant sont toutefois préservés pour pouvoir extraire
    les choices.
    """

    protected_body, protected = (
        _protect_inline_slice_literals(body)
    )

    chars = list(protected_body)

    depth = 0
    in_string = False
    escaped = False

    for i, char in enumerate(
        protected_body
    ):

        if in_string:

            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == '"':
                in_string = False

            if depth > 0:
                chars[i] = " "

            continue

        if char == '"':

            in_string = True

            if depth > 0:
                chars[i] = " "

        elif char == "{":

            depth += 1
            chars[i] = " "

        elif char == "}":

            chars[i] = " "
            depth = max(
                0,
                depth - 1
            )

        elif depth > 0:

            chars[i] = " "

    result = "".join(chars)

    # Restaurer uniquement les slices qui étaient
    # réellement au niveau courant. Celles situées
    # dans un bloc enfant auront déjà été effacées.
    for token, original in (
        protected.items()
    ):

        if token in result:
            result = result.replace(
                token,
                original,
            )

    return result

def extract_validation(body: str):
    out = {}

    # --------------------------------------------------------
    # Numeric range
    # --------------------------------------------------------

    m = re.search(
        r"validation\.IntBetween\("
        r"\s*(-?\d+)\s*,\s*(-?\d+)\s*\)",
        body,
    )

    if m:
        out["min"] = int(
            m.group(1)
        )

        out["max"] = int(
            m.group(2)
        )


    # --------------------------------------------------------
    # String length
    # --------------------------------------------------------

    m = re.search(
        r"validation\.StringLenBetween\("
        r"\s*(\d+)\s*,\s*(\d+)\s*\)",
        body,
    )

    if m:
        out["min_length"] = int(
            m.group(1)
        )

        out["max_length"] = int(
            m.group(2)
        )


    # --------------------------------------------------------
    # String choices
    # --------------------------------------------------------

    m = re.search(
        r"validation\.StringInSlice\("
        r"\s*\[\]\s*string\s*\{([^}]*)\}",
        body,
        re.S,
    )

    if m:

        vals = re.findall(
            r'"((?:\\.|[^"\\])*)"',
            m.group(1),
        )

        if vals:
            out["choices"] = vals


    # --------------------------------------------------------
    # Integer choices
    # --------------------------------------------------------

    m = re.search(
        r"validation\.IntInSlice\("
        r"\s*\[\]\s*int\s*\{([^}]*)\}",
        body,
        re.S,
    )

    if m:

        vals = re.findall(
            r"-?\d+",
            m.group(1),
        )

        if vals:
            out["choices"] = [
                int(value)
                for value in vals
            ]


    return out


def _parse_go_scalar_literal(value: str):
    """
    Parse uniquement les defaults Go simples.

    Support :
      "text"
      `text`
      true / false
      integer
      float

    Les expressions complexes restent volontairement
    non interprétées.
    """

    value = value.strip()

    if (
        len(value) >= 2
        and value[0] == '"'
        and value[-1] == '"'
    ):

        try:
            return ast.literal_eval(
                value
            )
        except Exception:
            return value[1:-1]


    if (
        len(value) >= 2
        and value[0] == "`"
        and value[-1] == "`"
    ):
        return value[1:-1]


    low = value.lower()

    if low == "true":
        return True

    if low == "false":
        return False


    if re.fullmatch(
        r"-?\d+",
        value,
    ):

        try:
            return int(value)
        except ValueError:
            pass


    if re.fullmatch(
        r"-?\d+\.\d+",
        value,
    ):

        try:
            return float(value)
        except ValueError:
            pass


    return None


def extract_default(body: str):
    """
    Extrait uniquement un Default Terraform explicite
    présent dans schema.Schema.

    Aucun default n'est inventé à partir de Computed,
    Optional ou de la documentation.
    """

    m = re.search(
        r"\bDefault\s*:\s*"
        r"("
        r'"(?:\\.|[^"\\])*"'
        r"|`[^`]*`"
        r"|true"
        r"|false"
        r"|-?\d+(?:\.\d+)?"
        r")"
        r"\s*,",
        body,
        re.S,
    )

    if not m:
        return None

    return _parse_go_scalar_literal(
        m.group(1)
    )

def parse_schema_entry(body: str):
    # Lire les propriétés uniquement au niveau courant.
    direct = direct_level_text(body)

    tm = re.search(
        r"\bType\s*:\s*schema\.(Type\w+)",
        direct
    )

    raw_type = tm.group(1) if tm else None

    out = {
        "type": canonical_type(raw_type),
        "raw_type": raw_type,
    }

    for key, go_key in [
        ("required", "Required"),
        ("optional", "Optional"),
        ("computed", "Computed"),
        ("force_new", "ForceNew"),
    ]:

        m = re.search(
            rf"\b{go_key}\s*:\s*(true|false)",
            direct
        )

        if m:
            out[key] = (
                m.group(1) == "true"
            )

    # IMPORTANT :
    # validation du parent uniquement.
    out.update(
        extract_validation(direct)
    )

    # Default Terraform explicite uniquement.
    default = extract_default(
        direct
    )

    if default is not None:
        out["default"] = default

    # Les enfants sont parsés séparément.
    nested = find_schema_map(body)

    if nested:
        out["children"] = {
            name: parse_schema_entry(child_body)
            for name, child_body
            in top_level_entries(nested)
        }

    return {
        k: v
        for k, v in out.items()
        if v is not None
    }

def resource_id(path: Path):
    base = path.stem.removeprefix("resource_")
    parts = base.split("_", 1)
    return ".".join(parts) if len(parts) == 2 else base


def extract_resource(path: Path, target_version: str, docs_dir: Path | None = None):
    text = path.read_text(encoding="utf-8", errors="replace")
    schema_block = find_schema_map(text)
    if not schema_block:
        return None
    rid = resource_id(path)
    attrs = {name: parse_schema_entry(body) for name, body in top_level_entries(schema_block)}
    support = None
    if docs_dir:
        doc = docs_dir / f"fortios_{path.stem.removeprefix('resource_')}.html.markdown"
        if doc.exists():
            dtext = doc.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"Applies to FortiOS Version\s*`([^`]+)`", dtext)
            if m:
                support = m.group(1).strip()
    item = {
        "id": rid,
        "version": target_version,
        "source_object": path.stem,
        "source": {"kind": "terraform", "file": str(path)},
        "attributes": attrs,
    }
    if support:
        item["declared_version_support"] = support
    return item


def extract_all(resources_dir: Path, target_version: str, out_dir: Path, docs_dir: Path | None = None):
    results, errors = [], []
    for path in sorted(resources_dir.glob("resource_*.go")):
        try:
            item = extract_resource(path, target_version, docs_dir)
            if item:
                results.append(item)
                dump_yaml(out_dir / f"{item['id']}.yaml", item)
        except Exception as exc:
            errors.append({"file": str(path), "error": repr(exc)})
    return results, errors
