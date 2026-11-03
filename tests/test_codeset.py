import os
import textwrap
import unittest

from icd10guard import CodeSet, normalize, parse_reference
from icd10guard.score import f1, score

HERE = os.path.dirname(__file__)

# Trimmed copy of real FY2026 tabular entries (A04, A05, A18, S22, E10, E11).
TABULAR = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <ICD10CM.tabular>
      <version>2026</version>
      <chapter>
        <name>1</name>
        <section id="A00-A09">
          <diag>
            <name>A04</name>
            <desc>Other bacterial intestinal infections</desc>
            <excludes1>
              <note>bacterial foodborne intoxications, NEC (A05.-)</note>
              <note>tuberculous enteritis (A18.32)</note>
            </excludes1>
            <diag><name>A04.0</name><desc>Enteropathogenic E. coli infection</desc></diag>
            <diag><name>A04.6</name><desc>Enteritis due to Yersinia enterocolitica</desc>
              <excludes1><note>extraintestinal yersiniosis (A28.2)</note></excludes1>
            </diag>
            <diag><name>A04.7</name><desc>Enterocolitis due to C. difficile</desc>
              <diag><name>A04.71</name><desc>recurrent</desc></diag>
              <diag><name>A04.72</name><desc>not specified as recurrent</desc></diag>
            </diag>
          </diag>
          <diag>
            <name>A05</name>
            <desc>Other bacterial foodborne intoxications, NEC</desc>
            <excludes1>
              <note>Escherichia coli infection (A04.0-A04.4)</note>
              <note>toxic effect of noxious foodstuffs (T61-T62)</note>
            </excludes1>
            <diag><name>A05.0</name><desc>Foodborne staphylococcal intoxication</desc></diag>
          </diag>
        </section>
      </chapter>
      <chapter>
        <name>4</name>
        <section id="E08-E13">
          <excludes1><note>neonatal diabetes mellitus (P70.2)</note></excludes1>
          <diag>
            <name>E10</name><desc>Type 1 diabetes mellitus</desc>
            <excludes1><note>type 2 diabetes mellitus (E11.-)</note></excludes1>
            <diag><name>E10.9</name><desc>Type 1 diabetes mellitus without complications</desc></diag>
          </diag>
          <diag>
            <name>E11</name><desc>Type 2 diabetes mellitus</desc>
            <excludes1><note>type 1 diabetes mellitus (E10.-)</note></excludes1>
            <diag><name>E11.9</name><desc>Type 2 diabetes mellitus without complications</desc></diag>
          </diag>
        </section>
      </chapter>
      <chapter>
        <name>19</name>
        <section id="S20-S29">
          <diag>
            <name>S22</name><desc>Fracture of rib(s), sternum and thoracic spine</desc>
            <diag><name>S22.4</name><desc>Multiple fractures of ribs</desc>
              <diag><name>S22.49</name><desc>Multiple fractures of ribs, unspecified side</desc></diag>
            </diag>
          </diag>
        </section>
      </chapter>
    </ICD10CM.tabular>
    """)

CODES = "\n".join([
    "A040    Enteropathogenic E. coli infection",
    "A046    Enteritis due to Yersinia enterocolitica",
    "A0471   Enterocolitis due to C. difficile, recurrent",
    "A0472   Enterocolitis due to C. difficile, not specified as recurrent",
    "A050    Foodborne staphylococcal intoxication",
    "E109    Type 1 diabetes mellitus without complications",
    "E119    Type 2 diabetes mellitus without complications",
    "S2249XA Multiple fractures of ribs, unspecified side, initial encounter",
]) + "\n"


def fixture(tmpdir):
    t = os.path.join(tmpdir, "tab.xml")
    c = os.path.join(tmpdir, "codes.txt")
    with open(t, "w") as f:
        f.write(TABULAR)
    with open(c, "w") as f:
        f.write(CODES)
    return CodeSet.load(t, c)


class ParseReferenceTest(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse_reference("x (A05.-)"), [("A05", "A05")])
        self.assertEqual(parse_reference("x (A04.7-)"), [("A047", "A047")])
        self.assertEqual(parse_reference("x (A18.32)"), [("A1832", "A1832")])
        self.assertEqual(parse_reference("x (A04.0-A04.4)"), [("A040", "A044")])
        self.assertEqual(parse_reference("x (T61-T62)"), [("T61", "T62")])
        self.assertEqual(parse_reference("x (E10.-, E11.-)"), [("E10", "E10"), ("E11", "E11")])

    def test_unparseable(self):
        self.assertIsNone(parse_reference("disorders of:"))
        self.assertIsNone(parse_reference("x - see categories E08-E10, E11"))
        self.assertIsNone(parse_reference("x (S02.- with 7th character B)"))

    def test_normalize(self):
        self.assertEqual(normalize(" s22.49xa "), "S2249XA")


class CodeSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._tmp = tempfile.TemporaryDirectory()
        cls.cs = fixture(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_status(self):
        self.assertEqual(self.cs.status("A04.71"), "billable")
        self.assertEqual(self.cs.status("A04.7"), "not_billable")  # needs a 5th character
        self.assertEqual(self.cs.status("S22.49"), "not_billable")  # needs a 7th character
        self.assertEqual(self.cs.status("s22.49xa"), "billable")
        self.assertEqual(self.cs.status("Z99.999"), "unknown")

    def test_seventh_character_maps_to_parent_node(self):
        self.assertEqual(self.cs.node_for("S2249XA"), "S2249")

    def test_excludes1_inherited_from_category(self):
        # note sits on A04, applies to its child A04.71
        ex = self.cs.excludes1_between("A04.71", "A05.0")
        self.assertIsNotNone(ex)
        self.assertEqual(ex.owner, "A04")

    def test_excludes1_range(self):
        self.assertIsNotNone(self.cs.excludes1_between("A05.0", "A04.0"))
        # A04.6 is outside A04.0-A04.4, but A04's own note still excludes A05
        ex = self.cs.excludes1_between("A04.6", "A05.0")
        self.assertEqual(ex.owner, "A04")

    def test_section_level_note(self):
        ex = self.cs.excludes1_between("E10.9", "P70.2")
        self.assertIsNotNone(ex)
        self.assertTrue(ex.owner.startswith("section"))

    def test_no_conflict_within_family_or_unrelated(self):
        self.assertIsNone(self.cs.excludes1_between("A04.71", "A04.72"))
        self.assertIsNone(self.cs.excludes1_between("A04.7", "A04.71"))
        self.assertIsNone(self.cs.excludes1_between("E11.9", "S22.49XA"))

    def test_check_reports_everything(self):
        issues = self.cs.check(["E10.9", "E11.9", "A04.7", "Q00.0"])
        kinds = sorted(i.kind for i in issues)
        self.assertEqual(kinds, ["excludes1", "not_billable", "unknown"])

    def test_score(self):
        self.assertAlmostEqual(f1(["E11.9"], ["E11.9", "A04.0"]), 2 / 3)
        self.assertEqual(f1(["E11.65"], ["E11.9"], level=3), 1.0)
        s = score(["E10.9", "E11.9"], ["E11.9"], self.cs)
        self.assertAlmostEqual(s["f1"], 2 / 3)
        self.assertAlmostEqual(s["penalized_f1"], 2 / 3 - 0.25)


@unittest.skipUnless(os.environ.get("ICD10_DATA"), "set ICD10_DATA to the CMS FY2026 files to run")
class RealDataTest(unittest.TestCase):
    def test_real_tables(self):
        d = os.environ["ICD10_DATA"]
        cs = CodeSet.load(os.path.join(d, "icd10cm_tabular_2026.xml"), os.path.join(d, "icd10cm_codes_2026.txt"))
        self.assertEqual(cs.version, "2026")
        self.assertEqual(cs.status("E11.9"), "billable")
        self.assertEqual(cs.status("E11"), "not_billable")
        self.assertIsNotNone(cs.excludes1_between("E10.9", "E11.9"))
        self.assertIsNotNone(cs.excludes1_between("A04.0", "A05.0"))
        self.assertIsNone(cs.excludes1_between("E11.9", "I10"))


if __name__ == "__main__":
    unittest.main()
