from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config import get_jwt_auth_manager, get_s3_storage_client
from database import UserGroupEnum, UserModel, UserProfileModel, get_db
from exceptions import BaseS3Error, BaseSecurityError
from schemas.profiles import ProfileCreateRequestSchema, ProfileResponseSchema
from security.http import get_token
from security.interfaces import JWTAuthManagerInterface
from storages import S3StorageInterface
from validation import validate_image

router = APIRouter()


async def get_current_user_id(
    token: str = Depends(get_token),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
) -> int:
    """
    Decode the access token extracted from the Authorization header and
    return the requester's user id.

    Raises:
        HTTPException: 401 Unauthorized if the token is invalid or expired.
    """
    try:
        payload = jwt_manager.decode_access_token(token)
    except BaseSecurityError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error

    return payload.get("user_id")


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create User Profile",
    description="Create a profile for the specified user. Requires a valid Bearer access token.",
    responses={
        401: {"description": "Unauthorized - missing/invalid/expired token, or user not found or not active."},
        403: {"description": "Forbidden - no permission to edit this profile."},
        400: {"description": "Bad Request - user already has a profile."},
        422: {"description": "Unprocessable Entity - invalid profile data."},
        500: {"description": "Internal Server Error - failed to upload avatar."},
    },
)
async def create_profile(
    user_id: int,
    avatar: UploadFile = File(...),
    profile_data: ProfileCreateRequestSchema = Depends(ProfileCreateRequestSchema.as_form),
    requester_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
) -> ProfileResponseSchema:
    """
    Create a new profile for the specified user.

    Behavior:
        1. Validates the Bearer token (see `get_current_user_id`).
        2. A user may only create their own profile unless they belong to the admin group.
        3. The target user must exist and be active.
        4. The target user must not already have a profile.
        5. The avatar is validated and uploaded to S3-compatible storage.
        6. The profile is stored in the database and returned.
    """
    stmt = (
        select(UserModel)
        .options(joinedload(UserModel.group))
        .where(UserModel.id == requester_id)
    )
    result = await db.execute(stmt)
    requester = result.scalars().first()

    if requester_id != user_id:
        is_admin = bool(requester and requester.group and requester.group.name == UserGroupEnum.ADMIN)
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this profile.",
            )

    if requester_id == user_id:
        target_user = requester
    else:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await db.execute(stmt)
        target_user = result.scalars().first()

    if not target_user or not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile.",
        )

    try:
        validate_image(avatar)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    avatar_bytes = await avatar.read()
    avatar_key = f"avatars/{user_id}_avatar.jpg"

    try:
        await s3_client.upload_file(file_name=avatar_key, file_data=avatar_bytes)
    except BaseS3Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later.",
        ) from error

    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=profile_data.gender,
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_key,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    response = ProfileResponseSchema.model_validate(new_profile)
    response.avatar = await s3_client.get_file_url(avatar_key)
    return response
