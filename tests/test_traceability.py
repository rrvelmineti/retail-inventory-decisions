"""Requirements traceability: every requirement is tested, and every test the UAT plan names exists."""
import importlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRD = (ROOT / "docs" / "business-requirements.md").read_text(encoding="utf-8")
UAT = (ROOT / "docs" / "uat-signoff.md").read_text(encoding="utf-8")


def requirements():
    return dict(re.findall(r"^\| (BR-\d\d) \| .*? \| ([MS]) \|", BRD, flags=re.M))


def cases():
    rows = re.findall(r"^\| (UAT-\d\d) \| ([^|]+) \| [^|]+ \| [^|]+ \| ([^|]+) \| ([^|]+) \|$", UAT, flags=re.M)
    return [{"id": c, "requirements": re.findall(r"BR-\d\d", reqs), "test": test.strip(), "result": result.strip()}
            for c, reqs, test, result in rows]


class TraceabilityTests(unittest.TestCase):
    def test_documents_parse(self):
        self.assertEqual(len(requirements()), 17)
        self.assertEqual(len(cases()), 27)

    def test_every_requirement_has_a_uat_case(self):
        covered = {r for c in cases() for r in c["requirements"]}
        self.assertEqual(set(requirements()) - covered, set())

    def test_cases_only_name_real_requirements(self):
        named = {r for c in cases() for r in c["requirements"]}
        self.assertEqual(named - set(requirements()), set())

    def test_every_automated_test_named_in_the_plan_exists(self):
        for c in cases():
            ref = c["test"].strip("`")
            if ref.startswith("Manual"):
                continue
            module, cls, method = ref.split(".")
            with self.subTest(case=c["id"]):
                test_class = getattr(importlib.import_module(f"tests.{module}"), cls)
                self.assertTrue(callable(getattr(test_class, method, None)), f"{ref} not found")

    def test_every_must_have_requirement_has_a_passing_case(self):
        passing = {r for c in cases() if c["result"].startswith("Pass") for r in c["requirements"]}
        must = {r for r, p in requirements().items() if p == "M"}
        self.assertEqual(must - passing, set())


if __name__ == "__main__":
    unittest.main()
