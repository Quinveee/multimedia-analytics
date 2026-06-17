import os

import config
from openai import OpenAI

_client = None
MOCK = os.getenv("MOCK", "false").lower() == "true"


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
    return _client


def _chat(messages: list[dict]) -> str:
    if MOCK:
        return "[MOCK] This is a dummy LLM response."
    resp = _get_client().chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        temperature=config.LLM_TEMPERATURE,
    )
    return resp.choices[0].message.content.strip()


def answer_closed(question: str) -> str:
    return _chat(
        [
            {
                "role": "system",
                "content": "Answer the question based on your knowledge.",
            },
            {"role": "user", "content": question},
        ]
    )


def answer_grounded(question: str, triples: str) -> str:
    system = (
        "You are given a set of knowledge graph triples. "
        "Answer the question using only the triples provided. "
        "Cite each fact as [T1], [T2], etc. based on the triple order.\n\n"
        f"Triples:\n{triples}"
    )
    return _chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
    )


def decompose_claims(answer: str) -> list[dict]:
    import re

    prompt = (
        "Break the following answer into a list of atomic factual claims. "
        "One claim per line, no bullet points. "
        "Do not include citation references like [T1] as separate claims — "
        "only extract the actual facts.\n\n"
        f"Answer: {answer}"
    )
    raw = _chat([{"role": "user", "content": prompt}])
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    claims = [l for l in lines if not re.fullmatch(r".*\[T\d+\].*", l)]

    result = []
    search_from = 0
    for claim in claims:
        idx = answer.find(claim, search_from)
        if idx != -1:
            result.append({"claim": claim, "start": idx, "end": idx + len(claim)})
            search_from = idx + len(claim)
        else:
            result.append({"claim": claim, "start": None, "end": None})
    return result
