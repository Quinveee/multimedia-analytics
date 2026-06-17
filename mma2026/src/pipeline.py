import argparse

import config
from services.kg import KG, triples_as_text
from services.llm import answer_closed, answer_grounded, decompose_claims
from services.spotlight import link_entities
from services.verifier import verify_claims


def run(question: str) -> dict:
    entities = link_entities(question)
    entity_uris = [e["uri"] for e in entities]

    subgraph = KG.get_subgraph(entity_uris, k=config.KG_HOP)
    triples = triples_as_text(subgraph)

    closed = answer_closed(question)
    grounded = answer_grounded(question, triples) if triples else closed

    claims = decompose_claims(grounded)
    verified = verify_claims(claims, triples)

    return {
        "question": question,
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
    args = parser.parse_args()

    result = run(args.question)

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
        print(f"[{c['label'].upper()}] {c['claim']}{span}")
