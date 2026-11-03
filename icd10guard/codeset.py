"""Load the CMS ICD-10-CM tabular list and check sets of codes against it.

Two checks matter for any model that outputs codes:
  * is every code a complete, billable code for this fiscal year (not a
    category header that still needs more characters, not a made-up code)?
  * does the set contain a pair that an Excludes1 note says must never be
    reported together?
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from itertools import combinations

CODE_RE = re.compile(r"^[A-Z][0-9][0-9A-Z](?:[0-9A-Z]{1,4})?$")
TRAILING_REF_RE = re.compile(r"\(([^()]*)\)\s*$")


def normalize(code: str) -> str:
    """'s22.49xa ' -> 'S2249XA'."""
    return code.strip().upper().replace(".", "")


def _clean_endpoint(tok: str) -> str | None:
    tok = tok.strip().rstrip("-").rstrip(".")
    tok = normalize(tok)
    return tok if CODE_RE.match(tok) else None


def parse_reference(text: str) -> list[tuple[str, str]] | None:
    """Parse the code reference of one Excludes1 note.

    Returns a list of (lo, hi) normalized prefixes. A single code or category
    gives lo == hi. Returns None when the note has no reference we can parse
    reliably (for example "see categories ..." or "with 7th character" forms).

    >>> parse_reference("bacterial foodborne intoxications, NEC (A05.-)")
    [('A05', 'A05')]
    >>> parse_reference("Escherichia coli infection (A04.0-A04.4)")
    [('A040', 'A044')]
    """
    m = TRAILING_REF_RE.search(text or "")
    if not m:
        return None
    out: list[tuple[str, str]] = []
    for part in re.split(r",\s*", m.group(1)):
        part = part.strip()
        if not part or " " in part:
            return None
        # "A04.7-" / "A05.-" / "T61-T62" / "A04.0-A04.4" / "M1A.-"
        body = part.rstrip("-").rstrip(".")
        ends = body.split("-")
        if len(ends) == 1:
            lo = _clean_endpoint(ends[0])
            if lo is None:
                return None
            out.append((lo, lo))
        elif len(ends) == 2:
            lo, hi = _clean_endpoint(ends[0]), _clean_endpoint(ends[1])
            if lo is None or hi is None:
                return None
            out.append((lo, hi))
        else:
            return None
    return out or None


def _in_range(code: str, lo: str, hi: str) -> bool:
    if lo == hi:
        return code.startswith(lo)
    return code[: len(lo)] >= lo and code[: len(hi)] <= hi


@dataclass(frozen=True)
class Exclusion:
    lo: str
    hi: str
    note: str
    owner: str  # code, section or chapter whose note this is

    def matches(self, code: str) -> bool:
        return _in_range(code, self.lo, self.hi)


@dataclass
class Issue:
    kind: str  # "unknown" | "not_billable" | "excludes1"
    codes: tuple[str, ...]
    detail: str = ""


@dataclass
class CodeSet:
    billable: set[str]
    parent: dict[str, str | None]
    exclusions: dict[str, tuple[Exclusion, ...]]
    unparsed_notes: list[str] = field(default_factory=list)
    version: str = ""

    # ---------- loading ----------
    @classmethod
    def load(cls, tabular_xml: str, codes_txt: str) -> "CodeSet":
        billable = set()
        with open(codes_txt, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    billable.add(line.split()[0].strip())

        root = ET.parse(tabular_xml).getroot()
        version = (root.findtext("version") or "").strip()
        parent: dict[str, str | None] = {}
        exclusions: dict[str, tuple[Exclusion, ...]] = {}
        unparsed: list[str] = []

        def own(el: ET.Element, owner: str) -> list[Exclusion]:
            found = []
            for ex in el.findall("excludes1"):
                for note in ex.findall("note"):
                    text = (note.text or "").strip()
                    refs = parse_reference(text)
                    if refs is None:
                        unparsed.append(f"{owner}: {text}")
                        continue
                    found.extend(Exclusion(lo, hi, text, owner) for lo, hi in refs)
            return found

        def walk_diag(el: ET.Element, par: str | None, inherited: tuple[Exclusion, ...]):
            code = normalize(el.findtext("name") or "")
            parent[code] = par
            eff = inherited + tuple(own(el, code))
            exclusions[code] = eff
            for child in el.findall("diag"):
                walk_diag(child, code, eff)

        for chapter in root.findall("chapter"):
            ch_ex = tuple(own(chapter, "chapter " + (chapter.findtext("name") or "")))
            for section in chapter.findall("section"):
                sec_ex = ch_ex + tuple(own(section, "section " + section.get("id", "")))
                for diag in section.findall("diag"):
                    walk_diag(diag, None, sec_ex)

        return cls(billable, parent, exclusions, unparsed, version)

    # ---------- lookups ----------
    def node_for(self, code: str) -> str | None:
        """Closest tabular entry for a code (7th-character codes are not listed
        in the tabular, so fall back to the longest listed prefix)."""
        c = normalize(code)
        while c:
            if c in self.parent:
                return c
            c = c[:-1]
        return None

    def status(self, code: str) -> str:
        c = normalize(code)
        if c in self.billable:
            return "billable"
        if c in self.parent:
            return "not_billable"
        return "unknown"

    def excludes1_between(self, a: str, b: str) -> Exclusion | None:
        a, b = normalize(a), normalize(b)
        if a.startswith(b) or b.startswith(a):
            return None
        for x, y in ((a, b), (b, a)):
            node = self.node_for(x)
            if node is None:
                continue
            for ex in self.exclusions.get(node, ()):
                if ex.matches(y) and not x.startswith(ex.lo):
                    return ex
        return None

    # ---------- checks ----------
    def check(self, codes) -> list[Issue]:
        uniq = sorted({normalize(c) for c in codes if c and c.strip()})
        issues: list[Issue] = []
        for c in uniq:
            st = self.status(c)
            if st != "billable":
                issues.append(Issue(st, (c,)))
        for a, b in combinations(uniq, 2):
            ex = self.excludes1_between(a, b)
            if ex is not None:
                issues.append(Issue("excludes1", (a, b), f"{ex.owner}: {ex.note}"))
        return issues
