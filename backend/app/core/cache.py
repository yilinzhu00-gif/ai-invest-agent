import hashlib


def secure_cache_key(
    workspace_id: str,
    acl_revision: str,
    normalized_input: str,
    model_version: str,
    prompt_version: str,
    retrieval_profile: str,
    as_of_date: str,
) -> str:
    raw = (
        f"{workspace_id}|{acl_revision}|{normalized_input}|{model_version}|{prompt_version}|"
        f"{retrieval_profile}|{as_of_date}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()
