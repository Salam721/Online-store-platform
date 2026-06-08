from pydantic import BaseModel, Field, validator
from decimal import Decimal

VALID_CATEGORIES = ['Electronics', 'Audio', 'Computers', 'Accessories', 'Home']

class ProductInput(BaseModel):
    title: str       = Field(min_length=1, max_length=200)
    category: str    = Field(min_length=1)
    description: str = Field(min_length=1, max_length=1000)
    price: Decimal   = Field(gt=0, max_digits=10, decimal_places=2)

    @validator('price')
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Price must be greater than zero')
        return v

    @validator('category')
    def category_must_be_valid(cls, v):
        if v not in VALID_CATEGORIES:
            raise ValueError(f'Invalid category: {v}. Must be one of {VALID_CATEGORIES}')
        return v

    class Config:
        json_encoders = {Decimal: lambda v: float(v)}
