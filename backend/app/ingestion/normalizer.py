import re


def normalize_retrieval_text(text: str) -> str:
    """Normalize whitespace only: signs, units, percentages and footnotes remain source-faithful."""
    return re.sub(r"[ \t]+", " ", text).strip()
