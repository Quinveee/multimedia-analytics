import os
from pathlib import Path

# Best-effort: load a .env (repo root or app/) so API keys can live in a file.
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass

# ── KG ────────────────────────────────────────────────────────────────────────
KG_PATH = Path(os.getenv("KG_PATH", "../offline/data/kg_subset.db"))
KG_HOP = int(os.getenv("KG_HOP", "1"))
KG_MAX_TRIPLES = int(os.getenv("KG_MAX_TRIPLES", "30"))

# ── Spotlight ─────────────────────────────────────────────────────────────────
SPOTLIGHT_URL = os.getenv(
    "SPOTLIGHT_URL", "http://localhost:2223/rest/annotate")

# ── LLM (all models served via OpenRouter) ────────────────────────────────────
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o")
ANSWER_MODEL = os.getenv("ANSWER_MODEL", DEFAULT_MODEL)
CLAIMS_MODEL = os.getenv("CLAIMS_MODEL", DEFAULT_MODEL)
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", DEFAULT_MODEL)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

# API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "dummy")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "dummy")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "dummy")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "dummy")
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# vLLM endpoints on Snellius
LLM_SMALL_URL = os.getenv("LLM_SMALL_URL", "http://localhost:8267/v1")
LLM_SMALL_MODEL = os.getenv("LLM_SMALL_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
LLM_SMALL_API_KEY = os.getenv("LLM_SMALL_API_KEY", "dummy")
LLM_BIG_URL = os.getenv("LLM_BIG_URL", "http://localhost:8268/v1")
LLM_BIG_MODEL = os.getenv("LLM_BIG_MODEL", "Qwen/Qwen3-VL-32B-Instruct")
LLM_BIG_API_KEY = os.getenv("LLM_BIG_API_KEY", "dummy")

# OpenRouter (OpenAI-compatible proxy)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "dummy")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def resolve_llm(model: str) -> tuple[str, str, str, str]:
    """Every model is served through OpenRouter (OpenAI-compatible).

    Returns (provider, base_url, api_key, model_name). ``model`` is an OpenRouter
    id such as "openai/gpt-4o" or "anthropic/claude-3.7-sonnet" (an optional
    "openrouter/" prefix is stripped).
    """
    name = model[len("openrouter/")
                     :] if model.lower().startswith("openrouter/") else model
    return "openrouter", OPENROUTER_BASE_URL, OPENROUTER_API_KEY, name


# ── Verifier ──────────────────────────────────────────────────────────────────
VERIFIER = os.getenv("VERIFIER", "llm")  # "llm" | "nli"
NLI_MODEL = os.getenv("NLI_MODEL", "cross-encoder/nli-deberta-v3-base")

# ── Mock ──────────────────────────────────────────────────────────────────────
MOCK = os.getenv("MOCK", "false").lower() == "true"

# ── UI Configuration ──────────────────────────────────────────────────────────
# UI configuration
IMAGE_GALLERY_SIZE = 24
IMAGE_GALLERY_ROW_SIZE = 4

WORDCLOUD_IMAGE_HEIGHT = 600
WORDCLOUD_IMAGE_WIDTH = 800

SCATTERPLOT_COLOR = "rgba(31, 119, 180, 0.5)"
SCATTERPLOT_SELECTED_COLOR = "red"

MAX_IMAGES_ON_SCATTERPLOT = 100

DEFAULT_PROJECTION = "UMAP"
DEFAULT_LEFT_WIDGET = "table"

GENERATED_IMAGE_SIZE = (200, 300)

# dataset extraction configuration
# number of images in the CUB-200-2011 dataset is 11788, that is the max value for this parameter
DATASET_SAMPLE_SIZE = 1000


# path configuration
ROOT_DIR = Path(__file__).parent.parent
DATASET_DIR = os.path.join(ROOT_DIR, "dataset")
DATA_DIR = os.path.join(DATASET_DIR, "data")
DOWNLOADS_DIR = os.path.join(DATASET_DIR, "downloads")
DATASET_PATH = os.path.join(DATA_DIR, "dataset.csv")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
AUGMENTED_DATASET_PATH = os.path.join(DATA_DIR, "augmented_dataset.csv")
ATTRIBUTE_DATA_PATH = os.path.join(DATA_DIR, "image_attributes.csv")
