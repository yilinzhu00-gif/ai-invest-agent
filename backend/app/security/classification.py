from enum import StrEnum


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class EgressPolicyError(Exception):
    pass


def allow_model_egress(classification: DataClassification, *, provider_is_third_party: bool) -> None:
    if classification is DataClassification.RESTRICTED and provider_is_third_party:
        raise EgressPolicyError("restricted_egress_denied")
