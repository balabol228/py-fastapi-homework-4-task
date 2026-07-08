from datetime import date

from fastapi import Form, HTTPException, status
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from validation import (
    validate_name,
    validate_gender,
    validate_birth_date
)


class ProfileCreateRequestSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_names(cls, value: str) -> str:
        validate_name(value)
        return value.lower()

    @field_validator("gender")
    @classmethod
    def validate_gender_field(cls, value: str) -> str:
        validate_gender(value)
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth_field(cls, value: date) -> date:
        validate_birth_date(value)
        return value

    @field_validator("info")
    @classmethod
    def validate_info_field(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Info field cannot be empty or contain only spaces.")
        return value

    @classmethod
    def as_form(
        cls,
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: str = Form(...),
        date_of_birth: date = Form(...),
        info: str = Form(...),
    ) -> "ProfileCreateRequestSchema":
        """
        Build and validate the schema from multipart/form-data fields.

        Converts any Pydantic validation error into an HTTP 422 response whose
        `detail` contains the original validation message.
        """
        try:
            return cls(
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                date_of_birth=date_of_birth,
                info=info,
            )
        except ValidationError as error:
            first_error = error.errors()[0]
            message = first_error["msg"]
            # Pydantic v2 prefixes messages raised from custom validators with "Value error, "
            if message.startswith("Value error, "):
                message = message[len("Value error, "):]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=message,
            ) from error


class ProfileResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str | None = None
