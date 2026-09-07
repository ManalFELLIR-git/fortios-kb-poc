from pathlib import Path
import shutil
import re

path = Path("kb_builder/terraform_extractor.py")

backup = Path(
    "kb_builder/terraform_extractor.py.before_choices_defaults.bak"
)

if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(
    encoding="utf-8"
)


# ============================================================
# 1. Ajouter import ast
# ============================================================

if "import ast" not in text:

    text = text.replace(
        "import re\n",
        "import re\nimport ast\n",
        1
    )


# ============================================================
# 2. Remplacer direct_level_text
# ============================================================

start = text.index(
    "def direct_level_text(body: str) -> str:"
)

end = text.index(
    "\ndef extract_validation(body: str):",
    start
)

new_direct = r'''def _protect_inline_slice_literals(text: str):
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
'''

text = (
    text[:start]
    + new_direct
    + text[end:]
)


# ============================================================
# 3. Remplacer extract_validation
#    + ajouter extract_default
# ============================================================

start = text.index(
    "def extract_validation(body: str):"
)

end = text.index(
    "\ndef parse_schema_entry(body: str):",
    start
)

new_validation = r'''def extract_validation(body: str):
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
'''

text = (
    text[:start]
    + new_validation
    + text[end:]
)


# ============================================================
# 4. Ajouter extraction Default dans parse_schema_entry
# ============================================================

needle = '''    out.update(
        extract_validation(direct)
    )
'''

replacement = '''    out.update(
        extract_validation(direct)
    )

    # Default Terraform explicite uniquement.
    default = extract_default(
        direct
    )

    if default is not None:
        out["default"] = default
'''

if needle not in text:
    raise RuntimeError(
        "Bloc extract_validation(direct) introuvable"
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
    "[OK] terraform_extractor.py patché"
)
print(
    "[OK] StringInSlice préservé"
)
print(
    "[OK] IntInSlice ajouté"
)
print(
    "[OK] Default explicite ajouté"
)
print(
    "[OK] Protection parent/enfants conservée"
)
print(
    "[BACKUP]",
    backup
)
