class JobRegistry:
    """In-process contract adapter; production task claims use a unique database constraint."""

    def __init__(self) -> None:
        self._claimed: set[tuple[str, str]] = set()

    def claim(self, workspace_id: str, key: str) -> bool:
        value = (workspace_id, key)
        if value in self._claimed:
            return False
        self._claimed.add(value)
        return True
