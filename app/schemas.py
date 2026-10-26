"""Request and response models."""
from typing import List, Optional

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class FormField(BaseModel):
    name: str
    label: str
    type: str
    required: bool = False


class DisplayOptions(BaseModel):
    color: str = "#0f3d3a"
    position: str = "bottom-right"


class WidgetCreate(BaseModel):
    type: str
    title: str
    description: Optional[str] = None
    form_fields: List[FormField]
    button_text: str = "Submit"
    display_options: DisplayOptions = DisplayOptions()


class WidgetUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    form_fields: Optional[List[FormField]] = None
    button_text: Optional[str] = None
    display_options: Optional[DisplayOptions] = None
