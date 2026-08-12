import io
import os
import uuid
from typing import BinaryIO

from fastapi import UploadFile

from app.core.config import settings


async def upload_cv_to_storage(candidate_id: int, original_filename: str, file_bytes: bytes, file_obj: BinaryIO | None = None) -> str:
    ext = os.path.splitext(original_filename or "cv.pdf")[1].lower() or ".pdf"
    unique_name = f"cvs/{candidate_id}/{uuid.uuid4()}{ext}"

    if settings.AWS_ACCESS_KEY_ID == "mock_access_key":
        os.makedirs(os.path.join("uploads", "cvs", str(candidate_id)), exist_ok=True)
        local_path = os.path.join("uploads", unique_name)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as buffer:
            buffer.write(file_bytes)
        return f"http://localhost:8000/uploads/{unique_name}"

    import boto3

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME,
    )
    s3.upload_fileobj(
        file_obj or io.BytesIO(file_bytes),
        settings.AWS_BUCKET_NAME,
        unique_name,
        ExtraArgs={"ContentType": "application/pdf"},
    )
    return f"https://{settings.AWS_BUCKET_NAME}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{unique_name}"


async def upload_cv_to_s3(candidate_id: int, file: UploadFile) -> str:
    file_bytes = await file.read()
    await file.seek(0)
    return await upload_cv_to_storage(candidate_id, file.filename or "cv.pdf", file_bytes, file.file)


async def delete_cv_file(resume_url: str) -> bool:
    if not resume_url or "localhost:8000/uploads/" not in resume_url:
        return True
    local_path = resume_url.replace("http://localhost:8000/uploads/", "uploads/")
    try:
        os.remove(local_path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
