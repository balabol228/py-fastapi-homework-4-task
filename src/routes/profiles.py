from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
import shutil

from database import get_db
from config.dependencies import get_s3_storage_client, get_jwt_auth_manager
from security.utils import get_token
from storages.interfaces import S3StorageInterface
from validation import validate_image

router = APIRouter(prefix="/users", tags=["Profiles"])

@router.post("/{user_id}/profile/", response_model=ProfileResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_profile(
    user_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: str = Form(...),
    info: str = Form(...),
    avatar: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
    jwt_manager = Depends(get_jwt_auth_manager),
    token: str = Depends(get_token)
):
    try:
        payload = jwt_manager.decode_token(token)
        current_user_id = payload.get("user_id")
        current_user_role = payload.get("role")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")

    if current_user_id != user_id and current_user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You don't have permission to edit this profile."
        )

    # 3. Перевірка існування та активності юзера
    # Тут робиш звичайний селект в базу:
    # user = await db.get(UserModel, user_id)
    # якщо не знайшли або не user.is_active:
    #     raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or not active.")

    # 4. Перевірка, чи профайл вже існує
    # Спроба дістати існуючий профайл за user_id. Якщо є:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already has a profile.")

    try:
        parsed_date = date.fromisoformat(date_of_birth)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    try:
        validate_image(avatar.file)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        object_name = f"avatars/{user_id}_avatar.jpg"
        file_content = await avatar.read()
        avatar_url = await s3_client.upload_file(file_content, object_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to upload avatar. Please try again later."
        )

    # 6. Створення запису в БД
    # new_profile = UserProfileModel(
    #     user_id=user_id, first_name=first_name, last_name=last_name, ... avatar=avatar_url
    # )
    # db.add(new_profile)
    # await db.commit()
    # await db.refresh(new_profile)

    return new_profile
