import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_official_host_policy_is_strict_but_supports_fred():
    module = load_script("check_release_links.py")
    assert module.official_host_allowed("www.sec.gov")
    assert module.official_host_allowed("fred.stlouisfed.org")
    assert not module.official_host_allowed("example.com")


def test_manifest_path_inventory_includes_initial_and_lazy_partitions():
    import json

    module = load_script("check_release_links.py")
    manifest = json.loads((ROOT / "pages-site" / "data" / "manifest.json").read_text())
    paths = module.manifest_paths(manifest)
    assert "partitions/overview.json" in paths
    assert any(path.startswith("partitions/timelines/") for path in paths)


def test_checksum_inventory_excludes_itself_and_covers_shell():
    module = load_script("build_release_checksum_inventory.py")
    payload = module.inventory()
    paths = {row["path"] for row in payload["files"]}
    assert "index.html" in paths
    assert "data/manifest.json" in paths
    assert "release-checksums.json" not in paths
    assert payload["summary"]["total_bytes"] > 0
