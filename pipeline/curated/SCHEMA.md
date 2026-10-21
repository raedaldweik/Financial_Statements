# Curated note overlay — schema

One JSON file per filing: `pipeline/curated/<id>.notes.json`.
It is merged by `pipeline/build_data.py` with the machine-extracted
`pipeline/out/<id>.notes.raw.json` (which supplies the full note text, pages
and auto-detected cross-references) into `data/<id>.js` for the dashboard.

```json
{
  "id": "aramco",
  "notes": [
    {
      "n": "24",
      "title": "Revenue",
      "category": "income",
      "summary": "Two to four plain-English sentences. State what the note discloses and quote the headline figures with the filing's unit (e.g. 'SAR 1,637,299 million'). No speculation.",
      "keyFigures": [
        {"label": "Revenue from contracts with customers", "v": ["1,630,366", "1,644,114"]}
      ],
      "subnotes": [
        {"id": "(a)", "title": "Transactions", "summary": "One sentence."}
      ],
      "refs": ["29"],
      "tags": ["revenue", "segments"],
      "investorRelevance": "One sentence: why a Ministry of Investment reviewer should open this note. null if routine.",
      "flag": {"level": "watch", "text": "One sentence describing the notable item."}
    }
  ]
}
```

Rules

- `n` is the note number as a string and must match the raw file.
- `title`: Title case, trimmed, no trailing punctuation. Fix ALL-CAPS titles.
- `category`: one of `policy`, `balance-sheet`, `income`, `equity`,
  `cash-flow`, `risk`, `group`, `tax`, `disclosure`.
- `keyFigures`: at most 6 rows. `v` is always a two-element array of strings
  copied exactly as printed in the filing, in the order [current year, prior
  year]. Use `"–"` when a value is absent. Negative numbers keep their
  parentheses. Omit the array (use `[]`) for narrative-only notes.
- `subnotes`: only genuine lettered/numbered sub-sections that exist in the
  note text (e.g. `(a)`, `(b)`, `16.1`, `A-`). Keep the id exactly as printed
  without trailing punctuation: `(a)`, `16.1`, `A`, `33-A`.
- `refs`: note numbers (strings) that this note's text explicitly refers to.
  Verify against the text; add any the extractor missed, drop false hits.
- `flag`: null unless the note contains something a reviewer must not miss:
  impairments, covenant breaches, qualified/other-matter paragraphs,
  restatements, going-concern language, large contingencies, concentration
  of customers/related parties, fires or other significant events, tax
  disputes. `level` is `info`, `watch` or `alert`.
- Every figure in `summary`, `keyFigures` and `flag` must come from the raw
  note text. Do not round unless the filing does.
