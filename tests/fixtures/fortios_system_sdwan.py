DOCUMENTATION = """
---
module: fortios_system_sdwan
options:
  system_sdwan:
    type: dict
    suboptions:
      status:
        description: Enable/disable SD-WAN.
        type: str
      new_8_only:
        description: Only in 8.
        type: str
      members:
        type: list
        suboptions:
          interface:
            description: Interface. Source system.interface.name.
            type: str
"""

versioned_schema = {
  "v_range": [["v6.4.0", ""]],
  "type": "dict",
  "children": {
    "status": {"v_range": [["v6.4.0", ""]], "type": "string", "options": [{"value":"disable"},{"value":"enable"}]},
    "new_8_only": {"v_range": [["v8.0.0", ""]], "type":"string"},
    "members": {"v_range": [["v6.4.0", ""]], "type":"list", "elements":"dict", "children": {
      "interface": {"v_range": [["v6.4.0", ""]], "type":"string"}
    }}
  }
}

def x(fos):
    fos.set("system", "sdwan", {})
