# Offline pipeline output schema

Frontend starts with `mock_kg.json`, real files swap in at integration with the same shape.

## `kg_subset.json`

```json
{
  "nodes": [
    {
      "id": "dbr:Marie_Curie",
      "label": "Marie Curie",
      "abstract": "Polish-French physicist...",
      "types": ["Person", "Scientist"],
      "image": "images/marie_curie.jpg"
    }
  ],
  "edges": [
    {
      "subject": "dbr:Marie_Curie",
      "predicate": "dbo:award",
      "object": "dbr:Nobel_Prize_in_Physics",
      "predicate_label": "award"
    }
  ]
}
```

- `image: null` = no image found (renders as dashed node in frontend)
- prefixes: `dbr:` = entity, `dbo:`/`dbp:` = predicate

## `validated_questions.json`

```json
[
  {
    "id": "1501",
    "question": "How many movies did Stanley Kubrick direct?",
    "gold_sparql": "SELECT DISTINCT COUNT(?uri) WHERE { ... }",
    "seed_uris": ["dbr:Stanley_Kubrick"],
    "evidence_triples": [
      {"subject": "dbr:...", "predicate": "dbo:director", "object": "dbr:Stanley_Kubrick"}
    ]
  }
]
```

`evidence_triples` = gold triples that answer the question, used for claim verification.
