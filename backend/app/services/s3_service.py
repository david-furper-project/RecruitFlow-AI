import boto3
import uuid
from fastapi import UploadFile
from app.core.config import settings

def get_s3_client():
    if settings.AWS_ACCESS_KEY_ID == "mock_access_key":
        class MockS3Client:
            def upload_fileobj(self, *args, **kwargs):
                pass
        return MockS3Client()
        
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME
    )

async def upload_cv_to_s3(candidate_id: int, file: UploadFile) -> str:
    """
    Uploads a CV to S3 and returns the public or presigned URL.
    """
    s3 = get_s3_client()
    
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"cvs/{candidate_id}/{uuid.uuid4()}.{file_extension}"
    
    await file.seek(0)
    
    if settings.AWS_ACCESS_KEY_ID == "mock_access_key":
        import os
        import shutil
        upload_dir = os.path.join("uploads", "cvs", str(candidate_id))
        os.makedirs(upload_dir, exist_ok=True)
        local_filepath = os.path.join("uploads", unique_filename)
        with open(local_filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        # Retornamos la URL local (FastAPI sirviendo los estáticos)
        return f"http://localhost:8000/uploads/{unique_filename}"
        
    s3.upload_fileobj(
        file.file,
        settings.AWS_BUCKET_NAME,
        unique_filename,
        ExtraArgs={"ContentType": "application/pdf"}
    )
    
    url = f"https://{settings.AWS_BUCKET_NAME}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{unique_filename}"
    return url
