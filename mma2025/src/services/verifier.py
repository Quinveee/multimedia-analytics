from services.llm import _chat


def verify_claims(claims: list[str], triples: str) -> list[dict]:
    results = []
    for claim in claims:
        prompt = (
            f"Given these knowledge graph triples:\n{triples}\n\n"
            f"Classify the following claim as one of: supported, inferred, unverifiable.\n"
            f"- supported: directly stated in the triples\n"
            f"- inferred: reasonable conclusion from the triples but not explicit\n"
            f"- unverifiable: cannot be determined from the triples\n\n"
            f"Claim: {claim}\n\n"
            f"Reply with only one word: supported, inferred, or unverifiable."
        )
        label = _chat([{"role": "user", "content": prompt}]).lower().strip()
        if label not in ("supported", "inferred", "unverifiable"):
            label = "unverifiable"
        results.append({"claim": claim, "label": label})
    return results
