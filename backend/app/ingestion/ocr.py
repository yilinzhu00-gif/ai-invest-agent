from typing import Protocol


class OCRExtractor(Protocol):
    async def extract(self, page_number: int, image_bytes: bytes) -> tuple[str, float]: ...
