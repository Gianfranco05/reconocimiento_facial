from pydantic import BaseModel


class ErrorOut(BaseModel):
    detail: str
    code: str


class BoundingBoxOut(BaseModel):
    x: int
    y: int
    width: int
    height: int
