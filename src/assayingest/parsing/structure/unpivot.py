"""The pure key-value/transposed un-pivot — grid in, (headers, rows) out
(SHAPE-02).

Pure module: no file I/O, no `pandas`, no `openpyxl`, no `anthropic` import —
the transform consumes the native-typed row tuples `structure/grid.py` reads
and a confirmed `SheetLayout`, so it is fully testable on hand-built tuples.

`unpivot_key_value` lands in the next task of this plan (12-01 Task 2,
TDD red-first); this module exists from Task 1 so the parametrized purity
guard in `tests/test_structure_layout.py` covers it from the moment the
verdict types exist.
"""

from __future__ import annotations
