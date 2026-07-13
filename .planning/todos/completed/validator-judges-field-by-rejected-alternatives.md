---
kind: bug
area: validation
surfaced_by: manual UAT 2026-07-12 (helixbio_export.csv + assay-potency, before the parser fix)
created: 2026-07-12
---

# The confirm gate can flag a field for a violation in a column the human already rejected

`validation/validator.py::_check_candidates` checks the chosen `source_column`
**and every ranked alternative** Claude proposed, and any violation among them
becomes the field's objection (VAL-02). That is right at *review* time — it
usefully surfaces "Claude's runner-up is garbage". It is wrong at the **confirm
gate**.

Once a human has explicitly chosen a column, the alternatives are no longer
candidate mappings — they are rejected suggestions. Nothing in the exported
data comes from them (`canonical.assemble` reads only `source_column`). But
`service.confirm()` re-runs `validate()` on a proposal whose `alternatives` the
client still carries verbatim (`state/review.ts::resolveByChip`/`resolveByDropdown`
change `source_column` and clear the amber flag but keep `alternatives`), so a
bad alternative re-flags the field, `is_ready` stays false, and the gate raises
`NotReadyError` — **forever**. The UI offers no way to remove an alternative,
so the human has no action that can clear it.

Observed live (on the pre-fix corrupted parse, but the mechanism is
parse-independent):

```
REJECTED assay_type: column 'Endpoint': '0.045' is not one of the allowed
values (IC50, EC50, Ki, Kd, %inhibition)
```

— while `assay_type`'s *chosen* column was `Compound Name`. The field was
condemned by a column the human was not using.

Same shape of dead end as the refuted-`date_format` bug closed in quick task
`260712-qgc`: the gate objects to something no Review-screen action can change.

## Likely fix

Validate alternatives at **mapping/review** time (keep VAL-02's warning value),
but have the **confirm gate** judge only the chosen `source_column` /
`inferred_value` — the only inputs the export actually reads. This is not a
weakening of the gate: a rejected alternative contributes nothing to the
assembled data, so checking it protects no value that will be written.

Do not "fix" this by having the client strip `alternatives` before confirming —
the server must not depend on the client for the gate's correctness (P1).

## Not currently reproducible with the shipped corpus

After the parser fix (`260712-r8b`), Claude returns clean mappings with no
alternatives on `helixbio_export.csv`, so the dead end does not currently fire
on the demo path. It remains a live defect for any file where Claude ranks an
alternative whose values violate the field's declared constraints.
