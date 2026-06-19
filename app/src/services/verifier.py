from src import config
from src.services.llm import _chat

_nli_model = None

_NLI_LABELS = ["contradiction", "entailment", "neutral"]


def _get_nli():
    global _nli_model
    if _nli_model is None:
        from sentence_transformers import CrossEncoder

        _nli_model = CrossEncoder(config.NLI_MODEL)
    return _nli_model


def _verify_llm(claim: str, triples: str) -> str:
    prompt = (
        f"Given these knowledge graph triples:\n{triples}\n\n"
        f"Classify the following claim as one of: supported, inferred, unverifiable.\n"
        f"- supported: directly stated in the triples\n"
        f"- inferred: reasonable conclusion from the triples but not explicit\n"
        f"- unverifiable: cannot be determined from the triples\n\n"
        f"Claim: {claim}\n\n"
        f"Reply with only one word: supported, inferred, or unverifiable."
    )
    label = (
        _chat([{"role": "user", "content": prompt}], model=config.VERIFIER_MODEL)
        .lower()
        .strip()
    )
    return (
        label if label in ("supported", "inferred", "unverifiable") else "unverifiable"
    )


def _verify_nli(claim: str, cited_triple_texts: list[str]) -> str:
    model = _get_nli()
    pairs = [(triple, claim) for triple in cited_triple_texts]
    scores = model.predict(pairs)
    labels = [_NLI_LABELS[s] for s in scores.argmax(axis=1)]
    if "entailment" in labels:
        return "supported"
    if "neutral" in labels:
        return "inferred"
    return "unverifiable"


def verify_claims(claims: list[dict], triples: str) -> list[dict]:
    triple_lines = [t for t in triples.splitlines() if t.strip()]
    results = []
    for c in claims:
        cited = c.get("cited_triples", [])
        if not cited:
            label = "unverifiable"
        else:
            cited_texts = [
                triple_lines[i - 1] for i in cited if 0 < i <= len(triple_lines)
            ]
            if config.VERIFIER == "nli":
                label = _verify_nli(c["claim"], cited_texts)
            else:
                label = _verify_llm(c["claim"], "\n".join(cited_texts))
        results.append({**c, "label": label})
    return results
