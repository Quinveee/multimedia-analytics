import argparse

from src import config
from src.services.kg import KG, rank_triples, verbalise_triples
from src.services.llm import (
    answer_closed,
    answer_grounded,
    parse_claims,
    parse_sentences,
)
from src.services.spotlight import link_entities
from src.services.verifier import verify_claims


def run_pipeline(
    question: str, answer_model: str = None, subgraph: dict = None
) -> dict:
    """Run the full grounding pipeline for a question.

    Args:
        question: natural language question
        answer_model: model identifier — "small" | "big" | "claude-*" | "gemini-*" | any OpenAI model.
                      Defaults to config.ANSWER_MODEL.
        subgraph: optional pre-filtered subgraph dict {"nodes": [...], "edges": [...]}.
                  If provided, skips KG retrieval.

    Returns:
        question        (str)        — original question
        answer_model    (str)        — resolved model name, e.g. "Qwen/Qwen3-VL-8B-Instruct"
        entities        (list[dict]) — Spotlight-linked entities: uri, surface_form, start, end
        subgraph        (dict)       — retrieved KG subgraph: nodes (id, label, types, image, _depth) + edges
        triples         (list[dict]) — ranked triples: subject, subject_label, predicate, predicate_label, object, object_label
        triples_prompt  (str)        — [T1] ... text used in the LLM prompt
        answer_closed   (str)        — closed-book answer (no KG context)
        answer_grounded (str)        — KG-grounded answer with inline [T#] citations
        claims_grounded (list[dict]) — verified claims from grounded answer: claim, cited_triples, start, end, label
        claims_closed   (list[dict]) — verified claims from closed-book answer: claim, start, end, label
    """
    answer_model = answer_model or config.ANSWER_MODEL

    # Link entities in the question and get their URIs
    entities = link_entities(question)
    entity_uris = [e["uri"] for e in entities]

    # If a subgraph is not provided, retrieve it from the KG using the entity URIs
    if subgraph is None:
        subgraph = KG.get_subgraph(entity_uris, k=config.KG_HOP)

    # Rank the triples in the subgraph and verbalise them for the LLM
    triples = rank_triples(subgraph, question)
    triples_prompt = verbalise_triples(subgraph, question)

    # Prepare image paths for entities that have associated images
    kg_dir = config.KG_PATH.parent
    image_paths = [
        str(kg_dir / n["image"])
        for n in subgraph["nodes"]
        if n.get("image") and n["id"] in entity_uris
    ]

    # Generate answers using the specified model
    closed = answer_closed(question, model=answer_model)
    grounded = (
        answer_grounded(
            question,
            triples_prompt,
            model=answer_model,
            image_paths=image_paths or None,
        )
        if triples_prompt
        else closed
    )

    # Verify the claims in both the grounded and closed-book answers against the triples prompt
    claims_grounded = verify_claims(parse_claims(grounded), triples_prompt)
    claims_closed = verify_claims(
        parse_sentences(closed), triples_prompt, verify_uncited=True
    )

    return {
        "question": question,
        "answer_model": config.resolve_llm(answer_model)[3],
        "entities": entities,
        "subgraph": subgraph,
        "triples": triples,
        "triples_prompt": triples_prompt,
        "answer_closed": closed,
        "answer_grounded": grounded,
        "claims_grounded": claims_grounded,
        "claims_closed": claims_closed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--answer-model",
        default=None,
        help="small | big | gpt-4o | claude-* | gemini-*",
    )
    args = parser.parse_args()

    result = run_pipeline(args.question, answer_model=args.answer_model)

    print(f"\n=== ANSWER MODEL: {result['answer_model']} ===")

    print("\n=== SUBGRAPH ===")
    print(
        f"{len(result['subgraph']['nodes'])} nodes, {len(result['subgraph']['edges'])} edges"
    )
    print(result["triples_prompt"] or "(no triples found)")

    print("\n=== CLOSED-BOOK ANSWER ===")
    print(result["answer_closed"])

    print("\n=== GROUNDED ANSWER ===")
    print(result["answer_grounded"])

    print("\n=== CLAIMS (grounded) ===")
    for c in result["claims_grounded"]:
        span = (
            f"  span=({c['start']}, {c['end']})"
            if c["start"] is not None
            else "  span=None"
        )
        cited = f"  cited={c['cited_triples']}" if c["cited_triples"] else ""
        print(f"[{c['label'].upper()}] {c['claim']}{cited}{span}")
