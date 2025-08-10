from pydantic import BaseModel


class EmailRequest(BaseModel):
    email_id: str
    subject: str
    message: str