import os
from pathlib import Path

# ── KG ────────────────────────────────────────────────────────────────────────
KG_PATH = Path(os.getenv("KG_PATH", "../offline/mock_kg.json"))
KG_HOP = int(os.getenv("KG_HOP", "1"))
KG_MAX_TRIPLES = int(os.getenv("KG_MAX_TRIPLES", "30"))

# ── Spotlight ─────────────────────────────────────────────────────────────────
SPOTLIGHT_URL = os.getenv("SPOTLIGHT_URL", "http://localhost:2223/rest/annotate")

# ── LLM ───────────────────────────────────────────────────────────────────────
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "small")
CLAIMS_MODEL = os.getenv("CLAIMS_MODEL", "small")
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "small")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

# API keys — each provider reads its own env var
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "dummy")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "dummy")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "dummy")

# vLLM endpoints on Snellius
LLM_SMALL_URL = os.getenv("LLM_SMALL_URL", "http://localhost:8267/v1")
LLM_SMALL_MODEL = os.getenv("LLM_SMALL_MODEL", "Qwen/Qwen2.5-7B-Instruct")
LLM_BIG_URL = os.getenv("LLM_BIG_URL", "http://localhost:8268/v1")
LLM_BIG_MODEL = os.getenv("LLM_BIG_MODEL", "Qwen/Qwen2.5-72B-Instruct")


def resolve_llm(model: str) -> tuple[str, str, str, str]:
    """Return (provider, base_url, api_key, model_name) from a model identifier."""
    m = model.lower()
    if m == "small":
        return "vllm", LLM_SMALL_URL, "dummy", LLM_SMALL_MODEL
    if m == "big":
        return "vllm", LLM_BIG_URL, "dummy", LLM_BIG_MODEL
    if m.startswith("claude"):
        return "anthropic", None, ANTHROPIC_API_KEY, model
    if m.startswith("gemini"):
        return (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            GEMINI_API_KEY,
            model,
        )
    return "openai", "https://api.openai.com/v1", OPENAI_API_KEY, model


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
DATASET_SAMPLE_SIZE = 1000  # number of images in the CUB-200-2011 dataset is 11788, that is the max value for this parameter


# path configuration
ROOT_DIR = Path(__file__).parent.parent
DATASET_DIR = os.path.join(ROOT_DIR, "dataset")
DATA_DIR = os.path.join(DATASET_DIR, "data")
DOWNLOADS_DIR = os.path.join(DATASET_DIR, "downloads")
DATASET_PATH = os.path.join(DATA_DIR, "dataset.csv")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
AUGMENTED_DATASET_PATH = os.path.join(DATA_DIR, "augmented_dataset.csv")
ATTRIBUTE_DATA_PATH = os.path.join(DATA_DIR, "image_attributes.csv")
