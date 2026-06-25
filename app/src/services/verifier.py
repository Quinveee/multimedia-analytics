import asyncio

from src import config
from src.services.llm import _achat

from sentence_transformers import CrossEncoder

_NLI_LABELS = ["contradiction", "entailment", "neutral"]
_nli_model = CrossEncoder(config.NLI_MODEL)


def _get_nli():
    return _nli_model


async def _verify_llm(claim: str, triples: str) -> str:
    """
    Classify a claim against triple text using an LLM. Returns supported/inferred/unverifiable.
    """
    prompt = (
        "Classify a claim against knowledge graph triples as: supported, inferred, or unverifiable.\n"
        "- supported: the claim is directly stated or clearly expressed by the triples (rephrasing counts as supported)\n"
        "- inferred: a reasonable conclusion from the triples but not explicitly stated\n"
        "- unverifiable: cannot be determined from the triples at all\n\n"
        "Examples:\n"
        "Triples: [T1] Ann Lewis birthPlace Jersey City, New Jersey | [T2] Ann Lewis birthPlace United States\n"
        "Claim: Ann Lewis was born in Jersey City, New Jersey, in the United States.\n"
        "Answer: supported\n\n"
        "Triples: [T1] Ann Lewis spouse Gerald A. Lewis\n"
        "Claim: Ann Lewis is married to Gerald A. Lewis.\n"
        "Answer: supported\n\n"
        "Triples: [T1] Ann Lewis office Counselor to the President | [T2] Ann Lewis president Bill Clinton\n"
        "Claim: Ann Lewis served as Counselor to the President under Bill Clinton.\n"
        "Answer: supported\n\n"
        "Triples: [T1] Marie Curie birthPlace Warsaw | [T2] Marie Curie award Nobel Prize in Physics\n"
        "Claim: Marie Curie was one of the greatest scientists of all time.\n"
        "Answer: inferred\n\n"
        "Triples: [T1] Marie Curie birthPlace Warsaw\n"
        "Claim: Marie Curie enjoyed living in Warsaw.\n"
        "Answer: unverifiable\n\n"
        f"Triples: {triples}\n"
        f"Claim: {claim}\n"
        "Answer:"
    )
    raw = await _achat(
        [{"role": "user", "content": prompt}], model=config.VERIFIER_MODEL
    )
    label = raw.lower().strip()
    return (
        label if label in ("supported", "inferred", "unverifiable") else "unverifiable"
    )


def _verify_nli(claim: str, cited_triple_texts: list[str]) -> str:
    """
    Classify a claim against triples using a cross-encoder NLI model. Returns supported/inferred/unverifiable.

    Each cited triple is checked individually (so a claim entailed by any single
    triple counts), and when a claim cites a few specific triples their
    conjunction is checked too, so a sentence supported only by the *combination*
    of facts (e.g. "a physicist born in Warsaw [T1][T2]") is not under-rated. The
    conjunction check is skipped when scanning many triples (closed-book), where
    any-match is the right semantics and a joined premise would overflow the model.
    """
    if not cited_triple_texts:
        return "unverifiable"
    model = _get_nli()
    pairs = [(triple, claim) for triple in cited_triple_texts]
    if 2 <= len(cited_triple_texts) <= 8:
        premise = ". ".join(t.strip().rstrip(".") for t in cited_triple_texts)
        pairs.append((premise, claim))
    scores = model.predict(pairs)
    labels = [_NLI_LABELS[s] for s in scores.argmax(axis=1)]
    if "entailment" in labels:
        return "supported"
    if "neutral" in labels:
        return "inferred"
    return "unverifiable"


async def verify_claims(
    claims: list[dict], triples: str, verify_uncited: bool = False, verifier: str = None
) -> list[dict]:
    """
    Verify each claim against its cited triples. The per-claim LLM checks run
    concurrently (asyncio.gather).

    verify_uncited=True: claims with no citations are verified against all triples (used for closed-book).
    verify_uncited=False: claims with no citations are marked unverifiable (used for grounded).
    verifier: "llm" | "nli" — overrides config.VERIFIER when given.
    """
    backend = (verifier or config.VERIFIER).lower()
    triple_lines = [t for t in triples.splitlines() if t.strip()]

    async def label_for(c: dict) -> dict:
        cited = c.get("cited_triples", [])
        if not cited:
            # claim grounded only in an entity's image — can't be checked against
            # triples; it carries its own "visual" state instead of unverifiable.
            if c.get("cited_images"):
                return {**c, "label": "visual"}
            if verify_uncited and triple_lines:
                cited_texts = triple_lines
            else:
                return {**c, "label": "unverifiable"}
        else:
            cited_texts = [
                triple_lines[i - 1] for i in cited if 0 < i <= len(triple_lines)
            ]
        if backend == "nli":
            # CPU-bound model; run off the event loop to keep it responsive.
            label = await asyncio.to_thread(_verify_nli, c["claim"], cited_texts)
        else:
            label = await _verify_llm(c["claim"], "\n".join(cited_texts))
        return {**c, "label": label}

    return list(await asyncio.gather(*(label_for(c) for c in claims)))
