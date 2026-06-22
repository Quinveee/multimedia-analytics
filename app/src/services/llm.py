import base64
import os
import re
from pathlib import Path

from src import config

MOCK = os.getenv("MOCK", "false").lower() == "true"

_openai_clients: dict = {}
_anthropic_client = None


def _get_openai_client(base_url: str, api_key: str):
    key = (base_url, api_key)
    if key not in _openai_clients:
        from openai import OpenAI

        kwargs = {"api_key": api_key, "base_url": base_url}
        if base_url and "openrouter" in base_url:
            # optional attribution headers, recommended by OpenRouter
            kwargs["default_headers"] = {
                "HTTP-Referer": "https://github.com/GoncaloBFM/mma2026",
                "X-Title": "KG Grounding Studio",
            }
        _openai_clients[key] = OpenAI(**kwargs)
    return _openai_clients[key]


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _anthropic_client


def _image_content(image_paths: list[str]) -> list[dict]:
    """
    Build OpenAI-style image content blocks from file paths.
    """
    blocks = []
    for p in image_paths:
        path = Path(p)
        if not path.exists():
            print(f"[llm] image not found: {path}")
            continue
        ext = path.suffix.lower().lstrip(".")
        media_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }.get(ext, "image/jpeg")
        data = base64.b64encode(path.read_bytes()).decode()
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{data}"},
            }
        )
    return blocks


def _to_anthropic_content(content) -> list[dict]:
    """
    Convert OpenAI-style content (str or list) to Anthropic format.
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    result = []
    for block in content:
        if block["type"] == "text":
            result.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image_url":
            url = block["image_url"]["url"]
            # data:<media_type>;base64,<data>
            header, data = url.split(",", 1)
            media_type = header.split(":")[1].split(";")[0]
            result.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )
    return result


def _chat(messages: list[dict], model: str = None) -> str:
    if MOCK:
        return "[MOCK] This is a dummy LLM response."

    model = model or config.ANSWER_MODEL
    provider, base_url, api_key, model_name = config.resolve_llm(model)

    if provider == "anthropic":
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_messages = [
            {**m, "content": _to_anthropic_content(m["content"])}
            for m in messages
            if m["role"] != "system"
        ]
        kwargs = {"model": model_name, "max_tokens": 1024, "messages": user_messages}
        if system:
            kwargs["system"] = system if isinstance(system, str) else system[0]["text"]
        resp = _get_anthropic_client().messages.create(**kwargs)
        return resp.content[0].text.strip()

    # openai / gemini / vllm
    resp = _get_openai_client(base_url, api_key).chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=config.LLM_TEMPERATURE,
    )
    return resp.choices[0].message.content.strip()


async def _achat(messages: list[dict], model: str = None) -> str:
    """Async chat completion via AsyncOpenAI (OpenRouter / OpenAI-compatible).

    The client is created per call (not cached): a cached AsyncOpenAI binds to a
    single event loop, and the Dash/asgiref callback loop may differ between
    requests, which would raise "event loop is closed".
    """
    if MOCK:
        return "[MOCK] This is a dummy LLM response."

    model = model or config.ANSWER_MODEL
    _provider, base_url, api_key, model_name = config.resolve_llm(model)

    from openai import AsyncOpenAI

    kwargs = {"api_key": api_key, "base_url": base_url}
    if base_url and "openrouter" in base_url:
        kwargs["default_headers"] = {
            "HTTP-Referer": "https://github.com/GoncaloBFM/mma2026",
            "X-Title": "KG Grounding Studio",
        }
    async with AsyncOpenAI(**kwargs) as client:
        resp = await client.chat.completions.create(
            model=model_name, messages=messages, temperature=config.LLM_TEMPERATURE
        )
    return resp.choices[0].message.content.strip()


async def answer_closed(question: str, model: str = None) -> str:
    return await _achat(
        [
            {
                "role": "system",
                "content": "Answer the question in a single short paragraph based on your knowledge. Do not use bullet points, lists, or headers.",
            },
            {"role": "user", "content": question},
        ],
        model=model,
    )


async def answer_grounded(
    question: str, triples: str, model: str = None, image_paths: list[str] = None
) -> str:
    system = (
        "Answer the question as a paragraph using ONLY the knowledge graph facts below. "
        "Each sentence must state exactly one fact and end with its citation. "
        "Do not use bullet points or lists. "
        "Do not combine multiple facts into one sentence.\n\n"
        "Make the text well formulated and sound."
        "Correct: 'Marie Curie was born in Warsaw. [T1] She died from aplastic anemia. [T5]'\n"
        "Wrong: 'Marie Curie was born in Warsaw and died from aplastic anemia. [T1][T5]'\n\n"
        "If the facts contain no relevant information, respond only with: "
        '"The provided facts do not contain enough information to answer this question."\n\n'
        f"Facts:\n{triples}"
    )
    image_blocks = _image_content(image_paths) if image_paths else []
    user_content = (
        [{"type": "text", "text": question}] + image_blocks
        if image_blocks
        else question
    )
    return await _achat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        model=model,
    )


def parse_claims(answer: str) -> list[dict]:
    """
    Parse [T#] citations from a grounded answer into one claim per citation.

    Boundaries are: start of text, after a period, or after a previous [T#].
    The text between the last boundary and a [T#] becomes one claim citing that triple.
    Any trailing text after the last [T#] is collected as an uncited claim.
    """
    matches = list(re.finditer(r"\[T(\d+)\]", answer))
    if not matches:
        clean = answer.strip()
        return (
            [{"claim": clean, "cited_triples": [], "start": 0, "end": len(answer)}]
            if clean
            else []
        )

    result = []
    last_boundary = 0

    for match in matches:
        t_idx = int(match.group(1))
        chunk = answer[last_boundary : match.start()]
        clean = re.sub(r"^[\s.,;]+", "", chunk).strip()
        if clean:
            result.append(
                {
                    "claim": clean,
                    "cited_triples": [t_idx],
                    "start": last_boundary,
                    "end": match.end(),
                }
            )
        last_boundary = match.end()

    # trailing uncited text
    tail = re.sub(r"^[\s.,;]+", "", answer[last_boundary:]).strip()
    if tail:
        result.append(
            {
                "claim": tail,
                "cited_triples": [],
                "start": last_boundary,
                "end": len(answer),
            }
        )

    return result


def parse_sentences(answer: str) -> list[dict]:
    """
    Split answer into sentences for closed-book claim verification.
    """
    parts = re.split(r"(?<=[.!?])\s+", answer.strip())
    result = []
    cursor = 0
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        idx = answer.find(sentence, cursor)
        if idx != -1:
            result.append(
                {
                    "claim": sentence,
                    "cited_triples": [],
                    "start": idx,
                    "end": idx + len(sentence),
                }
            )
            cursor = idx + len(sentence)
    return result


def decompose_claims(answer: str, model: str = None) -> list[dict]:
    """
    Obsolete (use parse_claims instead).
    """
    prompt = (
        "Break the following answer into a list of atomic factual claims. "
        "One claim per line, no bullet points. "
        "Do not include citation references like [T1] as separate claims, "
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
