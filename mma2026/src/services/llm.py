import os
import re

import config

MOCK = os.getenv("MOCK", "false").lower() == "true"

_openai_clients: dict = {}
_anthropic_client = None


def _get_openai_client(base_url: str, api_key: str):
    key = (base_url, api_key)
    if key not in _openai_clients:
        from openai import OpenAI

        _openai_clients[key] = OpenAI(api_key=api_key, base_url=base_url)
    return _openai_clients[key]


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _anthropic_client


def _chat(messages: list[dict], model: str = None) -> str:
    if MOCK:
        return "[MOCK] This is a dummy LLM response."

    model = model or config.ANSWER_MODEL
    provider, base_url, api_key, model_name = config.resolve_llm(model)

    if provider == "anthropic":
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_messages = [m for m in messages if m["role"] != "system"]
        kwargs = {"model": model_name, "max_tokens": 1024, "messages": user_messages}
        if system:
            kwargs["system"] = system
        resp = _get_anthropic_client().messages.create(**kwargs)
        return resp.content[0].text.strip()

    # openai / gemini / vllm
    resp = _get_openai_client(base_url, api_key).chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=config.LLM_TEMPERATURE,
    )
    return resp.choices[0].message.content.strip()


def answer_closed(question: str, model: str = None) -> str:
    return _chat(
        [
            {"role": "system", "content": "Answer the question based on your knowledge."},
            {"role": "user", "content": question},
        ],
        model=model,
    )


def answer_grounded(question: str, triples: str, model: str = None) -> str:
    system = (
        "You are given a set of knowledge graph facts.\n"
        "Answer the question using ONLY the facts provided below. "
        "Cite each fact you use as [T1], [T2], etc.\n"
        "If the facts do not contain enough information to answer the question, "
        'respond with: "The provided facts do not contain enough information to answer this question."\n\n'
        f"Facts:\n{triples}"
    )
    return _chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        model=model,
    )


def parse_claims(answer: str) -> list[dict]:
    """Parse [T#] citations from a grounded answer into one claim per citation.

    Boundaries are: start of text, after a period, or after a previous [T#].
    The text between the last boundary and a [T#] becomes one claim citing that triple.
    Any trailing text after the last [T#] is collected as an uncited claim.
    """
    matches = list(re.finditer(r"\[T(\d+)\]", answer))
    if not matches:
        clean = answer.strip()
        return [{"claim": clean, "cited_triples": [], "start": 0, "end": len(answer)}] if clean else []

    result = []
    last_boundary = 0

    for match in matches:
        t_idx = int(match.group(1))
        chunk = answer[last_boundary:match.start()]
        clean = re.sub(r"^[\s.,;]+", "", chunk).strip()
        if clean:
            result.append({
                "claim": clean,
                "cited_triples": [t_idx],
                "start": last_boundary,
                "end": match.end(),
            })
        last_boundary = match.end()

    # trailing uncited text
    tail = re.sub(r"^[\s.,;]+", "", answer[last_boundary:]).strip()
    if tail:
        result.append({
            "claim": tail,
            "cited_triples": [],
            "start": last_boundary,
            "end": len(answer),
        })

    return result


def decompose_claims(answer: str, model: str = None) -> list[dict]:
    """Obsolete — use parse_claims instead."""
    prompt = (
        "Break the following answer into a list of atomic factual claims. "
        "One claim per line, no bullet points. "
        "Do not include citation references like [T1] as separate claims — "
        "only extract the actual facts.\n\n"
        f"Answer: {answer}"
    )
    raw = _chat([{"role": "user", "content": prompt}], model=model)
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
