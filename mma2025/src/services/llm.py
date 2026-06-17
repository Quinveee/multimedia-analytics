import os
from openai import OpenAI

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "dummy"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        )
    return _client


MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


def _chat(messages: list[dict]) -> str:
    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


def answer_closed(question: str) -> str:
    return _chat([
        {"role": "system", "content": "Answer the question concisely based on your knowledge."},
        {"role": "user", "content": question},
    ])


def answer_grounded(question: str, triples: str) -> str:
    system = (
        "You are given a set of knowledge graph triples. "
        "Answer the question using only the triples provided. "
        "Cite each fact as [T1], [T2], etc. based on the triple order.\n\n"
        f"Triples:\n{triples}"
    )
    return _chat([
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ])


def decompose_claims(answer: str) -> list[str]:
    prompt = (
        "Break the following answer into a list of atomic factual claims. "
        "One claim per line, no bullet points.\n\n"
        f"Answer: {answer}"
    )
    raw = _chat([{"role": "user", "content": prompt}])
    return [line.strip() for line in raw.splitlines() if line.strip()]
