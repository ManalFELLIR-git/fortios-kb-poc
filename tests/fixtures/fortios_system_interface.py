DOCUMENTATION = """
---
module: fortios_system_interface
options:
  system_interface:
    type: dict
    suboptions:
      name:
        description: Explicit interface name fixture.
        type: str
"""

versioned_schema = {
    "v_range": [["v7.6.7", "v7.6.7"]],
    "type": "dict",
    "children": {
        "name": {"v_range": [["v7.6.7", "v7.6.7"]], "type": "string"},
    },
}


def configure(fos):
    fos.set("system", "interface", {})
