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


def _labeled_image_content(
    image_paths: list[str], image_labels: list[str] = None
) -> list[dict]:
    """
    Build image content blocks, each preceded by a ``[I#] Image of <label>:`` text
    marker so the model can cite what it sees in a specific image (see the [I#]
    citation rule in ``answer_grounded``). The id ``[I#]`` is the 1-based position
    in ``image_paths`` — kept stable even when a file is missing — so it matches
    the "Images" list in the system prompt and the ordering the pipeline records.
    """
    labels = image_labels or []
    blocks = []
    for i, p in enumerate(image_paths):
        img = _image_content([p])  # 0 (missing) or 1 block
        if not img:
            continue
        name = labels[i] if i < len(labels) and labels[i] else f"image {i + 1}"
        blocks.append({"type": "text", "text": f"[I{i + 1}] Image of {name}:"})
        blocks.append(img[0])
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
    question: str,
    triples: str,
    model: str = None,
    image_paths: list[str] = None,
    image_labels: list[str] = None,
) -> str:
    has_images = bool(image_paths)
    # The grounded answer may cite two kinds of source: text facts [T#] and, when
    # entity images are provided, what is visibly shown in them [I#]. Keeping the
    # two channels separate lets the UI flag image-grounded claims distinctly and
    # stops the model from pinning a visual observation onto an unrelated fact.
    image_rule = (
        " You are also shown labeled images of some entities (listed under \"Images\" "
        "below, each with an [I#] id). When a sentence relies on what is visibly shown "
        "in one of those images rather than a listed fact — an appearance, a depicted "
        "scene, a visual detail — cite it with its image id, like [I1], and state only "
        "what is actually visible. Never use [T#] for a purely visual observation, and "
        "never use [I#] for a textual fact."
        if has_images
        else ""
    )
    if has_images:
        labels = image_labels or []
        lines = "\n".join(
            f"[I{i + 1}] {labels[i] if i < len(labels) and labels[i] else f'image {i + 1}'}"
            for i in range(len(image_paths))
        )
        image_list = f"\n\nImages:\n{lines}"
        example_img = "Example image:\n[I1] (photograph of Marie Curie in her laboratory)\n"
        example_img_sentence = (
            " A photograph shows her working at a laboratory bench amid glassware [I1]."
        )
    else:
        image_list = example_img = example_img_sentence = ""
    system = (
        "Answer the question in a natural, fluent paragraph using ONLY the knowledge "
        "graph facts below"
        + (" and the entity images provided" if has_images else "")
        + ". Write the way a knowledgeable person would explain it: "
        "rephrase the facts into well-formed prose instead of copying them verbatim, "
        "and connect related facts smoothly. "
        "End each sentence with the fact ID(s) it relies on — use several, like "
        "[T2][T5], when a sentence draws on multiple facts. Every sentence that states "
        "a fact must carry at least one citation, and you may only state what the cited "
        "facts support." + image_rule + " "
        "Do not use bullet points, lists, or headers.\n\n"
        "Example facts:\n"
        "[T1] Marie Curie birthPlace Warsaw\n"
        "[T2] Marie Curie field Physics\n"
        "[T3] Marie Curie award Nobel Prize in Physics\n"
        + example_img
        + "Example answer: Marie Curie was a physicist born in Warsaw [T1][T2]. "
        "She went on to be awarded the Nobel Prize in Physics [T3]."
        + example_img_sentence
        + "\n\n"
        "If the facts do not contain enough information to answer, respond only with: "
        '"The provided facts do not contain enough information to answer this question."\n\n'
        f"Facts:\n{triples}" + image_list
    )
    image_blocks = (
        _labeled_image_content(image_paths, image_labels) if has_images else []
    )
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
    Parse a grounded answer into sentence-level claims with their [T#] citations.

    Splits the answer into sentences, absorbing any citations that trail the
    sentence-final punctuation (e.g. "... born in Warsaw. [T1]"), and collects
    every [T#] the sentence contains into ``cited_triples`` (a sentence may draw
    on several facts). A sentence carrying no citation yields ``cited_triples=[]``
    and is flagged unverifiable downstream. Sentence terminators inside decimals
    or abbreviations (no following whitespace) are not split on.

    Spans are contiguous and non-overlapping, covering the whole answer, so the
    frontend can highlight each claim directly.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"[.!?]+", answer):
        end = match.end()
        # absorb "[T#]" / "[I#]" citations trailing the period
        trailing = re.match(r"(?:\s*\[[TI]\d+\])+", answer[end:])
        if trailing:
            end += trailing.end()
        rest = answer[end:]
        if rest == "" or rest[:1].isspace():  # real boundary, not "2.5"
            if answer[start:end].strip():
                spans.append((start, end))
            start = end
    if answer[start:].strip():
        spans.append((start, len(answer)))

    result = []
    for s, e in spans:
        segment = answer[s:e]
        cited = list(dict.fromkeys(int(n) for n in re.findall(r"\[T(\d+)\]", segment)))
        # image citations [I#]: claims grounded in what an entity's image shows
        cited_images = list(
            dict.fromkeys(int(n) for n in re.findall(r"\[I(\d+)\]", segment))
        )
        claim = re.sub(r"\[[TI]\d+\]", "", segment)
        claim = re.sub(r"\s+([.,;:!?])", r"\1", claim)  # drop space left before punctuation
        claim = re.sub(r"\s+", " ", claim).strip()
        if claim:
            result.append(
                {
                    "claim": claim,
                    "cited_triples": cited,
                    "cited_images": cited_images,
                    "start": s,
                    "end": e,
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
