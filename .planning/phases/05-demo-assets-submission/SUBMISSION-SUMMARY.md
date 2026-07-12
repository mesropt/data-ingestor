# Submission summary (100–200 words)

<!-- Paste the block below into the submission form. Word count: ~155. -->

**Data Ingestor** turns the hours a data curator spends hand-reformatting every lab's differently-shaped CSV/Excel into a one-click review. You declare the target fields you want; Claude reads the messy file and proposes a column mapping with honest per-field confidence and a plain-English reason for each pick. Anything uncertain is flagged yellow — never a silent guess — and the human confirms or corrects it. Nothing is saved until every field is clear, and a no-LLM validator independently re-checks every value against your declared constraints, so the model never touches production truth directly ("trust the numbers").

Two things make it more than a wrapper. A **learning loop**: confirm one file from a lab, and the next file with the same column signature auto-maps at full confidence with zero Claude calls — the more it learns, the less your data leaves the building. And a **headers-only privacy mode** that sends column names, never cell values, to the API. Built domain-independent on synthetic data, proven across assay, PK, and genomics formats.
