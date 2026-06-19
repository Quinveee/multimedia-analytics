import argparse

from src import config
from src.services.kg import KG, verbalise_triples
from src.services.llm import answer_closed, answer_grounded, parse_claims
from src.services.spotlight import link_entities
from src.services.verifier import verify_claims


def run(question: str, answer_model: str = None, subgraph: dict = None) -> dict:
    answer_model = answer_model or config.ANSWER_MODEL

    entities = link_entities(question)
    entity_uris = [e["uri"] for e in entities]

    if subgraph is None:
        subgraph = KG.get_subgraph(entity_uris, k=config.KG_HOP)

    triples = verbalise_triples(subgraph, question, entity_uris)

    closed = answer_closed(question, model=answer_model)
    grounded = (
        answer_grounded(question, triples, model=answer_model) if triples else closed
    )

    claims = parse_claims(grounded)
    verified = verify_claims(claims, triples)

    return {
        "question": question,
        "answer_model": config.resolve_llm(answer_model)[3],
        "entities": entities,
        "subgraph": subgraph,
        "triples": triples,
        "answer_closed": closed,
        "answer_grounded": grounded,
        "claims": verified,
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

    result = run(args.question, answer_model=args.answer_model)

    print(f"\n=== ANSWER MODEL: {result['answer_model']} ===")

    print("\n=== SUBGRAPH ===")
    print(
        f"{len(result['subgraph']['nodes'])} nodes, {len(result['subgraph']['edges'])} edges"
    )
    print(result["triples"] or "(no triples found)")

    print("\n=== CLOSED-BOOK ANSWER ===")
    print(result["answer_closed"])

    print("\n=== GROUNDED ANSWER ===")
    print(result["answer_grounded"])

    print("\n=== CLAIMS ===")
    for c in result["claims"]:
        span = (
            f"  span=({c['start']}, {c['end']})"
            if c["start"] is not None
            else "  span=None"
        )
        cited = f"  cited={c['cited_triples']}" if c["cited_triples"] else ""
        print(f"[{c['label'].upper()}] {c['claim']}{cited}{span}")
