# Offline pipeline

This folder builds the data that the dashboard and the evaluation use. The idea
is to take the LC-QuAD questions plus the DBpedia 2016-04 dumps, build a small
knowledge graph around the entities the questions ask about, attach images to it,
and work out which questions can actually be answered from that graph. Everything
is built once and saved to files, so at runtime nothing has to talk to a live
SPARQL endpoint.

## The stages

main.py runs these in order. Each one reads what the previous ones wrote.

- extract_uris: read the gold query of each question and pull out the entities
  (the seeds) and the predicates it uses. Writes data/uris.json.
- neighbourhood: go through the DBpedia relation dumps and keep a triple whenever
  a seed is the subject or the object. That is one hop around each seed, which is
  enough to reach most answer entities. We kept it to one hop on purpose, two
  hops made the graph huge for very little extra coverage. Writes data/triples.json.
- enrich: build the graph from those triples and give each node a label, a short
  abstract and its types. Writes data/kg_subset.json.
- validate: run each gold query again against our triples and keep the questions
  that still return an answer, saving the exact triples that answer them. Writes
  data/validated_questions.json.
- clean_graph: drop the infobox junk. Keep the ontology relations (dbo) and the
  property relations (dbp) that questions actually ask about, drop everything
  else, plus edges that point to a missing node and nodes left with no edges.
  Edits data/kg_subset.json in place.
- images: attach an MMpedia image to the nodes that have one, but only for the
  entities that appear in the validated questions, otherwise it would download
  all of MMpedia. Writes data/images and data/coverage.csv.
- to_sqlite: pack the graph into a SQLite database the backend can query. Writes
  data/kg_subset.db.

(uri_norm.py in scripts/ is a small shared helper, not a stage. It puts two URIs
into the same form before we compare them, because DBpedia and the gold queries
do not always spell a URI the same way.)

## Running it

First install the requirements:

    pip install -r requirements.txt

You also need the DBpedia 2016-04 dumps. main.py downloads any that are missing
into dumps/, but they are large (a few hundred MB each), so the first run takes a
while. To run the whole pipeline, from this folder:

    python main.py

The images stage does not download anything unless you ask it to, because MMpedia
is very large. To let it fetch images, set an environment variable first:

    PowerShell:  $env:MMPEDIA_AUTO_DOWNLOAD = "1"; python main.py
    bash:        MMPEDIA_AUTO_DOWNLOAD=1 python main.py

By default it only gets images for the validated question entities. Set
MMPEDIA_FETCH_ALL=1 as well if you want an image for every node that has one.

If a download stops halfway, just run it again. Finished thumbnails are kept and
skipped, so it picks up where it left off instead of starting from scratch.

You can also run a single stage on its own, for example:

    python scripts/validate.py

## Folders

- scripts/: the pipeline stages, one file each.
- dumps/: the DBpedia dump files (downloaded, not kept in git).
- mmpedia/: the MMpedia index and archives (downloaded, not kept in git).
- qa_dataset/: the LC-QuAD train and test json.
- data/: everything the pipeline produces.
- tests/: unit tests. Run them with:

      python -m unittest discover -s tests

## Using kg_subset.db from the backend

The database has two tables, nodes and edges. To draw the part of the graph
around one entity, get its node and the edges touching it:

    SELECT * FROM nodes WHERE id = ?;
    SELECT * FROM edges WHERE subject = ? OR object = ?;

There is an index on edges.subject and edges.object, so those neighborhood
lookups are fast, and id is the primary key of nodes so looking a node up by id
is fast too. The types column comes back as a json string, so json.loads it to
get the list. The image column is the thumbnail path, or NULL when there is no
image.

## The evidence file

validated_questions.json is the important one for the evaluation. For each kept
question it lists evidence_triples, the exact triples from the graph that answer
it. Those are the gold labels used later to check whether an answer is really
supported by the graph.

There is a longer, more technical writeup in DESIGN.md at the repo root if you
want the reasons behind the design choices.
