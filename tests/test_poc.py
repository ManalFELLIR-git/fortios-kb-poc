from pathlib import Path
from kb_builder.ansible_extractor import extract_module
from kb_builder.terraform_extractor import extract_resource
from kb_builder.fortinet_docs import parse_cli_page

FIX = Path(__file__).parent / "fixtures"

def test_ansible_version_filter():
    d = extract_module(FIX/"fortios_system_sdwan.py", "7.6.7")
    assert d["id"] == "system.sdwan"
    assert "status" in d["attributes"]
    assert "new_8_only" not in d["attributes"]
    assert d["attributes"]["status"]["choices"] == ["disable","enable"]
    assert d["attributes"]["members"]["children"]["interface"]["references"] == ["system.interface.name"]


def test_terraform_parser():
    d = extract_resource(FIX/"resource_system_sdwan.go", "7.6.7")
    assert d["id"] == "system.sdwan"
    assert d["attributes"]["duplication_max_num"]["min"] == 2
    assert d["attributes"]["duplication_max_num"]["max"] == 4
    assert d["attributes"]["members"]["children"]["interface"]["max_length"] == 15


def test_cli_parser():
    html = (FIX/"cli_sdwan.html").read_text()
    d = parse_cli_page(html, "https://example", "7.6.7")
    assert d["id"] == "system.sdwan"
    assert d["attributes"]["status"]["default"] == "disable"
    assert d["attributes"]["duplication-max-num"]["max"] == 4
    assert d["children"]["members"]["attributes"]["interface"]["max_length"] == 15
