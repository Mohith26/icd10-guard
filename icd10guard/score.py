"""Set-level scoring for predicted vs gold ICD-10-CM code lists."""

from __future__ import annotations

from .codeset import CodeSet, normalize


def f1(pred, gold, level: int | None = None) -> float:
    """Set F1. level=3 compares categories only (first 3 characters)."""
    def prep(codes):
        s = {normalize(c) for c in codes if c and c.strip()}
        return {c[:level] for c in s} if level else s

    p, g = prep(pred), prep(gold)
    if not p and not g:
        return 1.0
    tp = len(p & g)
    if tp == 0:
        return 0.0
    prec, rec = tp / len(p), tp / len(g)
    return 2 * prec * rec / (prec + rec)


def score(pred, gold, codeset: CodeSet | None = None, penalty: float = 0.25) -> dict:
    """Strict F1, category F1, and (with a CodeSet) a validity-penalized F1.

    The penalized score subtracts `penalty` per invalid or Excludes1 issue in
    the prediction and floors at 0, so a grader prefers a slightly less
    complete code set over one that cannot be billed as written.
    """
    out = {"f1": f1(pred, gold), "category_f1": f1(pred, gold, level=3)}
    if codeset is not None:
        issues = codeset.check(pred)
        out["issues"] = [(i.kind, i.codes) for i in issues]
        out["penalized_f1"] = max(0.0, out["f1"] - penalty * len(issues))
    return out
