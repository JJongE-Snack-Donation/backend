from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
import os
import logging
from PIL import Image
from datetime import datetime
from .exifparser import process_images
from .database import db
from .utils.response import standard_response, handle_exception
from .utils.constants import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    THUMBNAIL_SIZE,
    MESSAGES
)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__)

def allowed_file(filename: str) -> bool:
    """허용된 파일 확장자 검사"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_thumbnail(image_path: str, thumbnail_path: str) -> bool:
    """썸네일 이미지 생성"""
    try:
        with Image.open(image_path) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            img.save(thumbnail_path, "JPEG")
        return True
    except Exception as e:
        logger.error(f"Error creating thumbnail for {image_path}: {str(e)}")
        return False

@upload_bp.route('/files/upload', methods=['POST'])
@jwt_required()
def upload_files():
    """파일 업로드 API"""
    try:
        if 'files' not in request.files:
            return standard_response(MESSAGES['error']['invalid_request'], status=400)

        files = request.files.getlist('files')
        project_info = request.form.get('project_info')
        
        if not files or not project_info:
            return standard_response(MESSAGES['error']['invalid_request'], status=400)

        uploaded_files = []
        for file in files:
            if file and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    continue

                filename = secure_filename(file.filename)
                file_path = os.path.join('uploads', filename)
                
                # 파일 저장
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                
                # 썸네일 생성
                thumbnail_path = os.path.join('thumbnails', filename)
                if create_thumbnail(file_path, thumbnail_path):
                    uploaded_files.append({
                        'filename': filename,
                        'path': file_path,
                        'thumbnail': thumbnail_path
                    })

        if uploaded_files:
            # EXIF 데이터 처리 및 DB 저장
            processed_images = process_images(
                [f['path'] for f in uploaded_files],
                project_info,
                'analysis',
                str(datetime.utcnow())
            )
            
            return standard_response(
                MESSAGES['success']['upload'],
                data={'uploaded_files': uploaded_files}
            )

        return standard_response(MESSAGES['error']['invalid_request'], status=400)

    except Exception as e:
        return handle_exception(e)

@upload_bp.route('/files/delete/<image_id>', methods=['DELETE'])
@jwt_required()
def delete_file(image_id):
    """파일 삭제 API"""
    try:
        image = db.images.find_one_and_delete({'_id': image_id})
        
        if not image:
            return standard_response(MESSAGES['error']['not_found'], status=404)

        # 실제 파일 삭제
        for path in [image.get('FilePath'), image.get('ThumnailPath')]:
            if path and os.path.exists(path):
                os.remove(path)

        return standard_response(MESSAGES['success']['delete'])

    except Exception as e:
        return handle_exception(e)

