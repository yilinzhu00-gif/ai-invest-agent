HARD_GATES = frozenset({"schema", "numeric", "citation", "acl", "no_answer", "tool_policy"})


def score_gates(gates: dict[str, bool]) -> tuple[dict[str, float], bool]:
    scores = {gate: float(gates.get(gate, False)) for gate in HARD_GATES}
    return scores, all(score == 1 for score in scores.values())
