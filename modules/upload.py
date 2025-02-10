from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
import os
import logging
from PIL import Image
from datetime import datetime
from .exifparser import process_images
from .database import db
import json
from bson.objectid import ObjectId
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
        project_info = request.form.get('project_info')  # FormData에서 project_info 가져오기
        
        if not files or not project_info:
            return standard_response(MESSAGES['error']['invalid_request'], status=400)

        try:
            project_info_json = json.loads(project_info)  # JSON 문자열을 파싱
            project_id = project_info_json.get('project_id')
            if not project_id:
                return standard_response("프로젝트 ID가 필요합니다", status=400)
                
            # 프로젝트 정보 조회
            project = db.projects.find_one({'_id': ObjectId(project_id)})
            if not project:
                return standard_response("프로젝트를 찾을 수 없습니다", status=400)
                
            formatted_project_info = {
                'name': project['project_name'],
                'id': str(project['_id'])
            }
            
        except json.JSONDecodeError:
            return standard_response("잘못된 프로젝트 정보 형식입니다", status=400)

        uploaded_files = []
        for file in files:
            if file and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    continue

                filename = secure_filename(file.filename)
                base_path = os.path.abspath(f"./mnt/{project_id}/analysis")  # 절대 경로로 변환
                file_path = os.path.join(base_path, "source", filename)
                thumbnail_path = os.path.join(base_path, "thumbnail", f"thum_{filename}")
                
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                file.save(file_path)
                
                if create_thumbnail(file_path, thumbnail_path):
                    uploaded_files.append({
                        'filename': filename,
                        'path': file_path,  # 절대 경로 저장
                        'thumbnail': thumbnail_path,
                        'project_id': project_id
                    })

        if uploaded_files:
            processed_images = process_images(
                [f['path'] for f in uploaded_files],
                formatted_project_info,
                'analysis',
                str(datetime.utcnow())
            )
            
            return standard_response(
                MESSAGES['success']['upload'],
                data={'uploaded_files': uploaded_files}
            )

        return standard_response(MESSAGES['error']['invalid_request'], status=400)

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
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

@upload_bp.route('/files/bulk-delete', methods=['DELETE'])
@jwt_required()
def delete_multiple_files():
    """다중 파일 삭제 API"""
    try:
        # 요청 데이터 확인
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        
        if not image_ids:
            return standard_response("삭제할 이미지 ID가 필요합니다", status=400)
            
        deleted_count = 0
        failed_ids = []
        
        for image_id in image_ids:
            try:
                # 이미지 정보 조회 및 삭제
                image = db.images.find_one_and_delete({'_id': image_id})
                
                if image:
                    # 실제 파일 삭제
                    for path in [image.get('FilePath'), image.get('ThumnailPath')]:
                        if path and os.path.exists(path):
                            os.remove(path)
                    deleted_count += 1
                else:
                    failed_ids.append(image_id)
                    
            except Exception as e:
                failed_ids.append(image_id)
                continue
        
        response_message = f"{deleted_count}개의 파일이 삭제되었습니다."
        if failed_ids:
            response_message += f" {len(failed_ids)}개의 파일 삭제 실패."
            
        return standard_response(
            message=response_message,
            data={'failed_ids': failed_ids}
        )

    except Exception as e:
        return handle_exception(e)

