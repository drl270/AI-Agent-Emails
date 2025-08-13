from enum import Enum
from typing import Dict, List

from pydantic import BaseModel


class Category(Enum):
    ORDER = "order"
    INQUIRY = "inquiry"
    COMPLAINT = "complaint"
    STATUS = "status"
    UNKNOWN = "unknown"

class CustomerMessage(BaseModel):
    id: str
    subject: str
    body: str
    first_name: str
    last_name: str
    title: str
    products_purchase: List[str]
    products_inquiry: List[str]
    category: Category
    history: List[str]
    formatted_summary: str
    order_details: Dict
    response: str

class VerificationResult(BaseModel):
    first_name: bool
    last_name: bool
    title: bool
    category: bool
    products_purchase: bool
    products_inquiry: bool
    occasion: bool

class State:
    def __init__(self):
        self.customer_message = CustomerMessage(
            id="",
            subject="",
            body="",
            first_name="",
            last_name="",
            title="",
            products_purchase=[],
            products_inquiry=[],
            category=Category.UNKNOWN,
            history=[],
            formatted_summary="",
            order_details={},
            response=""
        )
        self.verification_result = VerificationResult(
            first_name=False,
            last_name=False,
            title=False,
            category=False,
            products_purchase=False,
            products_inquiry=False,
            occasion=False
        )