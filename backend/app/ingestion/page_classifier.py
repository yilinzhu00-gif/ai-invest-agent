from enum import Enum


class PageKind(str, Enum):
    NATIVE = "native"
    OCR = "ocr"


def classify_page(native_text: str, *, minimum_characters: int = 40) -> PageKind:
    """Native text wins; sparse/empty pages are the only OCR candidates."""
    return PageKind.NATIVE if len(native_text.strip()) >= minimum_characters else PageKind.OCR
