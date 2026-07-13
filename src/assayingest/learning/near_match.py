"""Near-miss header matching: a header that is almost a spelling the crosswalk
already knows (`Tset` for `Test`, `Reuslt` for `Result`, `Unts` for `Units`).

A PROPOSAL, never an application. Nothing here maps a column, edits a header, or
touches a value — it returns "this header resembles that known alias" and the
human decides. That is not timidity: a header is what tells the tool which
COLUMN a number came from, and in a clinical file `Cl` (chloride) and `Ca`
(calcium) are one character apart. A near match applied silently would put the
right-looking number under the wrong field, produce a clean table, and pass the
validator — which knows constraints, not truth. So the near match is offered,
in amber, and dies unconfirmed.

Two guards make the offer safe to show at all:

* **Transpositions count as ONE edit** (Damerau, not plain Levenshtein). Real
  typing errors are overwhelmingly transpositions — `Tset`/`Test`,
  `Reuslt`/`Result` — and plain Levenshtein scores those 2, the same as two
  unrelated substitutions. Scoring them 1 is what lets the threshold stay tight
  enough to reject `Ca`/`Cl` while still catching the typos this exists for.

* **Ambiguity kills the suggestion.** If a header sits equally close to aliases
  of two DIFFERENT canonical fields, no candidate is returned at all. A tie is
  precisely the case where a wrong guess is most likely and most harmful, and
  "I am not sure, so here is a coin toss" is the one answer this tool never
  gives.

Once the curator confirms a mapping, the header is recorded in the crosswalk as
a real alias with its provenance — so the NEXT file from that vendor with the
same typo matches deterministically, at full confidence, with no model call and
no question. The tool learns to read the vendor; it never rewrites the vendor's
file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

#: The most edits a header may be from a known alias and still be offered. Two
#: covers the observed typo classes (a transposition plus a dropped letter);
#: three starts admitting genuinely different words.
_MAX_EDITS = 2

#: ...and no more than this share of the alias's length, so the absolute bound
#: cannot wave through a near-total rewrite of a short name. `Ca` -> `Cl` is 1
#: edit over 2 characters (0.50) and is REJECTED here; `Tset` -> `Test` is 1
#: over 4 (0.25) and passes. This ratio is the guard that makes a two-letter
#: analyte code safe.
_MAX_EDIT_RATIO = 0.34


@dataclass(frozen=True)
class NearMatch:
    """One header that is almost a known alias — a candidate, never a mapping."""

    header: str
    #: The canonical field the resembled alias belongs to.
    field: str
    #: The known spelling it resembles — the curator's evidence. Showing only
    #: the field ("Tset -> analyte?") asks them to trust the tool; showing the
    #: alias ("Tset looks like Test") lets them check it.
    resembles: str
    edits: int


def normalise(text: str) -> str:
    """The comparison form: case- and whitespace-insensitive, punctuation-free.

    Mirrors what the exact alias index already does, so a header the index would
    have matched EXACTLY can never also arrive here as a near match.
    """
    return "".join(ch for ch in text.strip().lower() if ch.isalnum() or ch.isspace())


def damerau_levenshtein(a: str, b: str) -> int:
    """Edit distance where a transposition of two adjacent characters costs 1.

    Optimal string alignment: enough for typos (it does not handle an edit that
    spans an already-transposed pair, which no real typo does) and it stays a
    simple two-dimensional table.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    before_previous: list[int] = []
    for i, ch_a in enumerate(a, start=1):
        current = [i]
        for j, ch_b in enumerate(b, start=1):
            cost = 0 if ch_a == ch_b else 1
            best = min(
                current[j - 1] + 1,          # insertion
                previous[j] + 1,             # deletion
                previous[j - 1] + cost,      # substitution
            )
            if (
                i > 1
                and j > 1
                and ch_a == b[j - 2]
                and a[i - 2] == ch_b
            ):
                best = min(best, before_previous[j - 2] + 1)  # transposition
            current.append(best)
        before_previous, previous = previous, current
    return previous[-1]


def near_match_for(header: str, alias_index: Mapping[str, str | None]) -> NearMatch | None:
    """The one known alias this header is almost certainly a misspelling of, or
    `None` when there is no close spelling — or more than one.

    `alias_index` is the SAME normalised header->field map the exact scorer uses
    (`service._vendor_agnostic_alias_index`), so the two can never disagree about
    what counts as a known spelling.

    Returns `None`, deliberately, when:

    * the header matches an alias EXACTLY (the exact scorer already has it, and a
      near match would be a second, weaker answer to a settled question);
    * nothing is within the edit bounds;
    * the closest aliases belong to two DIFFERENT canonical fields — a tie is
      not a weak answer, it is the absence of one.

    A tie between two aliases of the SAME field is fine and does not suppress the
    suggestion: `Reuslt` resembling both `Result` and `Results` still says
    `result`, and the curator is being asked about the FIELD.
    """
    needle = normalise(header)
    if not needle or needle in alias_index:
        return None

    best: list[tuple[int, str, str]] = []  # (edits, field, alias spelling)
    for known, field in alias_index.items():
        if field is None:
            continue
        edits = damerau_levenshtein(needle, known)
        if edits > _MAX_EDITS or edits > len(known) * _MAX_EDIT_RATIO:
            continue
        best.append((edits, field, known))

    if not best:
        return None

    best.sort(key=lambda candidate: (candidate[0], candidate[1], candidate[2]))
    fewest = best[0][0]
    fields_at_best = {field for edits, field, _ in best if edits == fewest}
    if len(fields_at_best) > 1:
        # Equally close to two different fields. This is the `Ca`/`Cl` case, and
        # the honest answer is silence -- the human still sees the column in the
        # "no field in this Schema" row and can map it themselves.
        return None

    edits, field, alias = best[0]
    return NearMatch(header=header, field=field, resembles=alias, edits=edits)
