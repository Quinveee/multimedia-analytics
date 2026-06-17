import config
from services.llm import _chat

_nli_pipe = None


def _get_nli():
    global _nli_pipe
    if _nli_pipe is None:
        from transformers import pipeline
        _nli_pipe = pipeline("zero-shot-classification", model=config.NLI_MODEL)
    return _nli_pipe


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
    label = _chat([{"role": "user", "content": prompt}]).lower().strip()
    return label if label in ("supported", "inferred", "unverifiable") else "unverifiable"


def _verify_nli(claim: str, triple_list: list[str]) -> str:
    nli = _get_nli()
    best_score, best_label = 0.0, "unverifiable"
    for triple in triple_list:
        result = nli(claim, candidate_labels=["entailment", "neutral", "contradiction"],
                     hypothesis_template="{}", multi_label=False)
        scores = dict(zip(result["labels"], result["scores"]))
        if scores.get("entailment", 0) > 0.7 and scores["entailment"] > best_score:
            best_score = scores["entailment"]
            best_label = "supported"
        elif scores.get("neutral", 0) > 0.6 and best_label == "unverifiable":
            best_label = "inferred"
    return best_label


def verify_claims(claims: list[str], triples: str) -> list[dict]:
    triple_list = [t for t in triples.splitlines() if t.strip()]
    results = []
    for claim in claims:
        if config.VERIFIER == "nli":
            label = _verify_nli(claim, triple_list)
        else:
            label = _verify_llm(claim, triples)
        results.append({"claim": claim, "label": label})
    return results
