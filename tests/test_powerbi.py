"""The committed Power BI project must match its generator, and every reference in it must resolve."""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"


def load(name):
    spec = importlib.util.spec_from_file_location(name, PBI / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_files(root):
    """Generated files only; Power BI Desktop's own .pbi folders are ignored."""
    files = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and rel.startswith("RetailInventory") and "/.pbi/" not in rel:
            files[rel] = path.read_bytes()
    return files


class PowerBIProjectTests(unittest.TestCase):
    def test_committed_project_matches_the_generator(self):
        builder = load("build_pbip")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "assets").mkdir()
            (out / "assets" / "CY24SU10.json").write_bytes((PBI / "assets" / "CY24SU10.json").read_bytes())
            builder.HERE = out                      # the base theme is copied from HERE/assets
            builder.build(out)
            fresh = project_files(out)
        committed = project_files(PBI)
        self.assertEqual(sorted(fresh), sorted(committed), "Run python powerbi/build_pbip.py and commit the result.")
        for name, data in fresh.items():
            self.assertEqual(data, committed[name], f"{name} is out of date; rerun python powerbi/build_pbip.py")

    def test_every_json_file_parses_and_declares_a_schema(self):
        files = list(PBI.glob("RetailInventory*/**/*.json")) + list(PBI.glob("RetailInventory*.pbip"))
        self.assertGreater(len(files), 25)
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if "StaticResources" not in path.parts:
                self.assertTrue(doc.get("$schema", "").startswith("https://developer.microsoft.com/json-schemas/"), path)

    def test_every_visual_field_exists_in_the_model(self):
        self.assertEqual(load("check_pbip").check_visual_fields(), [])

    def test_tmdl_declares_every_table_and_indents_with_tabs(self):
        definition = PBI / "RetailInventory.SemanticModel" / "definition"
        refs = set(re.findall(r"^ref table '?([^'\n]+?)'?$", (definition / "model.tmdl").read_text(), re.M))
        tables = {re.search(r"^table '?([^'\n]+?)'?$", p.read_text(), re.M).group(1)
                  for p in (definition / "tables").glob("*.tmdl")}
        self.assertEqual(refs, tables)
        for path in definition.rglob("*.tmdl"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertFalse(line.startswith(" "), f"{path.name}:{n} must indent with tabs")


if __name__ == "__main__":
    unittest.main()
