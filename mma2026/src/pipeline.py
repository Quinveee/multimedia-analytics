import argparse
import json
from services.kg import load_kg, get_subgraph, triples_as_text
from services.llm import answer_closed, answer_grounded, decompose_claims
from services.verifier import verify_claims


def run(question: str, kg_path=None) -> dict:
    kg = load_kg(kg_path) if kg_path else load_kg()
    subgraph = get_subgraph(question, kg)
    triples = triples_as_text(subgraph)

    closed = answer_closed(question)
    grounded = answer_grounded(question, triples) if triples else closed

    claims = decompose_claims(grounded)
    verified = verify_claims(claims, triples)

    return {
        "question": question,
        "subgraph": subgraph,
        "triples": triples,
        "answer_closed": closed,
        "answer_grounded": grounded,
        "claims": verified,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--kg", default=None, help="path to kg_subset.json")
    args = parser.parse_args()

    result = run(args.question, args.kg)

    print("\n=== SUBGRAPH ===")
    print(f"{len(result['subgraph']['nodes'])} nodes, {len(result['subgraph']['edges'])} edges")
    print(result["triples"] or "(no triples found)")

    print("\n=== CLOSED-BOOK ANSWER ===")
    print(result["answer_closed"])

    print("\n=== GROUNDED ANSWER ===")
    print(result["answer_grounded"])

    print("\n=== CLAIMS ===")
    for c in result["claims"]:
        span = f"  span=({c['start']}, {c['end']})" if c["start"] is not None else "  span=None"
        print(f"[{c['label'].upper()}] {c['claim']}{span}")
