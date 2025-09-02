from enum import Enum
from typing import Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class Category(Enum):
    ORDER = "order"
    INQUIRY = "inquiry"
    ORDER_INQUIRY = "order_inquiry"
    COMPLAINT = "complaint"
    STATUS = "status"
    UNKNOWN = "unknown"

class OrderStatus(Enum):
    FILLED = "filled"
    PARTIAL = "partial"
    NONE = "none"

class Product(BaseModel):
    product_name: str
    product_description: str
    quantity: int
    product_id: str
    filled: int = 0
    unfilled: int = 0
    order_status: OrderStatus = OrderStatus.NONE
    price: int = 0

class CustomerMessage(BaseModel):
    id: str = ""
    subject: str = ""
    body: str = ""
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    products_purchase: List[Product] = Field(default_factory=list)
    products_inquiry: List[Product] = Field(default_factory=list)
    products_recommendations: List[Product] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    category: Category = Category.UNKNOWN
    history: List[str] = Field(default_factory=list)
    formatted_summary: str = ""
    order_details: Dict = Field(default_factory=dict)
    response: str = ""
    occasion: str = ""
    language: str = ""

class VerificationResult(BaseModel):
    first_name: bool = False
    last_name: bool = False
    title: bool = False
    category: bool = False
    products_purchase: bool = False
    products_inquiry: bool = False
    occasion: bool = False


class State(TypedDict):
    customer_message: Optional[CustomerMessage]
    verification_result: Optional[VerificationResult]