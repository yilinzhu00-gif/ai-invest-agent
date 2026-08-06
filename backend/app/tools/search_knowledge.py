from pydantic import BaseModel, Field


class SearchKnowledgeInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


class SearchKnowledgeOutput(BaseModel):
    evidence_ids: list[str]
