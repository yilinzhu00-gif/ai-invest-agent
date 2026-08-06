from pydantic import BaseModel, Field


class QueryTableInput(BaseModel):
    table_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=1000)


class QueryTableOutput(BaseModel):
    cells: list[dict[str, object]]
