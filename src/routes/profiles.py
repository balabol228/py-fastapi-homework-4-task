from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field, field_validator, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, UserModel, UserProfileModel
from security import get_current_user
from storage import upload_avatar_to_minio


router = APIRouter()


class ProfileRequestSchema(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    gender: str = Field(..., min_length=1)
    birth_date: date
    info: str = Field(..., min_length=1)

    @field_validator("birth_date", mode="before")
    @classmethod
    def validate_birth_date(cls, value):
        if isinstance(value, str):
            value = date.fromisoformat(value)
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise ValueError("User must be 18 years or older.")
        return value


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    birth_date: date
    info: str
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


@router.post(
    "/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create User Profile"
)
async def create_profile(
    first_name: str = Form(...),
    last_name: str = Form(...),
    gender: str = Form(...),
    birth_date: str = Form(...),
    info: str = Form(...),
    avatar: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[UserModel] = Depends(get_current_user),
) -> ProfileResponseSchema:
    """
    Create a new user profile with schema validation and optional avatar upload.
    """
    if not current_user or not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    stmt = select(UserProfileModel).where(UserProfileModel.user_id == current_user.id)
    result = await db.execute(stmt)
    existing_profile = result.scalars().first()

    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile."
        )

    try:
        profile_data = ProfileRequestSchema(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            birth_date=birth_date,
            info=info
        )
    except ValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err.errors()[0]["msg"]
        )

    avatar_url = None
    if avatar:
        avatar_url = await upload_avatar_to_minio(avatar, current_user.id)

    new_profile = UserProfileModel(
        user_id=current_user.id,
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=profile_data.gender,
        birth_date=profile_data.birth_date,
        info=profile_data.info,
        avatar_url=avatar_url
    )

    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return ProfileResponseSchema.model_validate(new_profile)
