"""Validate every JSON file in the Power BI project against Microsoft's published JSON schemas.

    git clone --depth 1 --filter=blob:none --sparse https://github.com/microsoft/json-schemas
    git -C json-schemas sparse-checkout set fabric
    python powerbi/check_pbip.py path/to/json-schemas

Also checks that every field a visual uses exists in the semantic model.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREFIX = "https://developer.microsoft.com/json-schemas/"


def registry(root):
    from referencing import Registry, Resource

    def retrieve(uri):
        if not uri.startswith(PREFIX):
            raise LookupError(uri)
        return Resource.from_contents(json.loads((root / uri[len(PREFIX):]).read_text(encoding="utf-8")))
    return Registry(retrieve=retrieve)


def validate_json(root):
    from jsonschema import Draft7Validator, Draft202012Validator

    reg, problems, checked = registry(root), [], 0
    for path in sorted(HERE.glob("RetailInventory*/**/*.json")) + sorted(HERE.glob("RetailInventory*.pbip")) + \
            sorted(HERE.glob("RetailInventory*/*.pbi?")) + sorted(HERE.glob("RetailInventory*/.platform")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        uri = doc.get("$schema") if isinstance(doc, dict) else None
        if not uri:
            if "StaticResources" in path.parts:
                continue  # themes have no published per-file schema
            problems.append(f"{path.relative_to(HERE)}: no $schema")
            continue
        schema = json.loads((root / uri[len(PREFIX):]).read_text(encoding="utf-8"))
        cls = Draft202012Validator if "2020-12" in schema.get("$schema", "") else Draft7Validator
        for err in cls(schema, registry=reg).iter_errors(doc):
            problems.append(f"{path.relative_to(HERE)} at {'/'.join(map(str, err.absolute_path)) or '(root)'}: {err.message[:300]}")
        checked += 1
    return checked, problems


def model_fields():
    """Tables, columns and measures declared in the TMDL files."""
    fields = {}
    for path in (HERE / "RetailInventory.SemanticModel" / "definition" / "tables").glob("*.tmdl"):
        text = path.read_text(encoding="utf-8")
        table = re.search(r"^table (.+)$", text, re.M).group(1).strip("'")
        names = re.findall(r"^\t(?:column|measure) ('(?:[^']|'')+'|[^\s=]+)", text, re.M)
        fields[table] = {n.strip("'").replace("''", "'") for n in names}
    return fields


def check_visual_fields():
    fields, problems = model_fields(), []
    for path in HERE.glob("RetailInventory.Report/definition/pages/*/visuals/*/visual.json"):
        text = path.read_text(encoding="utf-8")
        for entity, prop in re.findall(r'"Entity": "([^"]+)"\s*}\s*},\s*"Property": "([^"]+)"', text):
            if prop not in fields.get(entity, ()):
                problems.append(f"{path.relative_to(HERE)}: {entity}[{prop}] is not in the model")
    return problems


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "json-schemas")
    checked, problems = validate_json(root)
    problems += check_visual_fields()
    for p in problems:
        print("PROBLEM", p)
    print(f"Checked {checked} JSON files against Microsoft's schemas: {len(problems)} problems.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
