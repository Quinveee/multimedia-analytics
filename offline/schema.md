# Data file formats

This lists every file the pipeline writes into data/, what it holds and what it
looks like. The frontend can start from mock_kg.json, the real kg_subset.json has
the same shape and swaps in later.

Two things to keep in mind:

- triples.json uses the full URIs (the validate stage needs real IRIs to run the
  gold queries). Everything meant for the frontend (kg_subset.json, the db, the
  evidence) uses the short prefixes instead.
- Short prefixes: dbr: is an entity, dbo: is an ontology relation or type, dbp:
  is an infobox property relation, rdf: is rdf:type.


## uris.json

Made by stage 1. For every question, the entities and predicates its gold query
uses, plus the global sets of all of them. URIs are the full form here.

```json
{
  "entities": ["http://dbpedia.org/resource/'03_Bonnie_&_Clyde", "..."],
  "predicates": ["http://dbpedia.org/ontology/academicAdvisor", "..."],
  "per_question": {
    "1501": {
      "entities": ["http://dbpedia.org/resource/Stanley_Kubrick"],
      "predicates": ["http://dbpedia.org/ontology/director"]
    }
  }
}
```


## triples.json

Made by stage 2. The relations we kept around the seed entities, as a flat list.
Full URIs, subject predicate object. This is what the validate stage queries.

```json
[
  {
    "s": "http://dbpedia.org/resource/Alain_Connes",
    "p": "http://dbpedia.org/ontology/field",
    "o": "http://dbpedia.org/resource/Mathematics"
  }
]
```


## kg_subset.json

Made by stage 3, then cleaned by stage 6 and given images by stage 5. This is the
graph the frontend draws. Short prefixes, and each node carries its label, a short
abstract, its types and an image path.

```json
{
  "nodes": [
    {
      "id": "dbr:Marie_Curie",
      "label": "Marie Curie",
      "abstract": "Polish-French physicist known for research on radioactivity.",
      "types": ["Person", "Scientist"],
      "image": "images/Marie_Curie.jpg"
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

image is null when there is no picture for that node (the frontend can draw it as
a dashed node). predicate_label is just the predicate name without the prefix.


## validated_questions.json

Made by stage 4. The questions that still have an answer in our graph. For each
one it keeps the original question text, the gold query, the seeds and the exact
triples that answer it. This is the main file the evaluation uses. Prefixes are
short here.

```json
[
  {
    "id": "2653",
    "question": "What is the river whose mouth is in deadsea?",
    "gold_sparql": "SELECT DISTINCT ?uri WHERE { ?uri <http://dbpedia.org/ontology/riverMouth> <http://dbpedia.org/resource/Dead_Sea> . ?uri <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://dbpedia.org/ontology/River> }",
    "seed_uris": ["dbr:Dead_Sea"],
    "evidence_triples": [
      {"subject": "dbr:Jordan_River", "predicate": "dbo:riverMouth", "object": "dbr:Dead_Sea"},
      {"subject": "dbr:Jordan_River", "predicate": "rdf:type", "object": "dbo:River"}
    ]
  }
]
```

evidence_triples are the gold triples that answer the question, used later to
check whether an answer is really supported by the graph.


## coverage.csv

Made by stage 5. One row per node. Says whether MMpedia has an image for it (and
how many), plus a few simple stats. has_image here means MMpedia has a picture
available, which is not the same as us having downloaded a thumbnail for it.
types is the node types joined with a pipe.

```text
entity,has_image,n_images,degree,abstract_len,types
dbr:!Kung_language,False,0,2,506,Language
dbr:!PAUS3,True,1,3,266,MusicalArtist
```


## kg_subset.db

Made by stage 7. The same graph as kg_subset.json but in SQLite, so the backend
can fetch part of it without loading the whole json. Two tables, with indexes on
the edge endpoints. types is stored as a json string, image is the path or NULL.

```sql
CREATE TABLE nodes (id TEXT PRIMARY KEY, label TEXT, abstract TEXT, types TEXT, image TEXT);
CREATE TABLE edges (subject TEXT, predicate TEXT, object TEXT, predicate_label TEXT);
CREATE INDEX idx_edges_subject ON edges(subject);
CREATE INDEX idx_edges_object  ON edges(object);
```

To get one node and everything connected to it:

```sql
SELECT * FROM nodes WHERE id = ?;
SELECT * FROM edges WHERE subject = ? OR object = ?;
```


## images/

Made by stage 5. A folder of 256px jpg thumbnails, one per entity that had an
image. A node points at its file through the image field, for example
"images/Marie_Curie.jpg".
