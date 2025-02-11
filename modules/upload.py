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
        project_info = request.form.get('project_info')
        
        if not files or not project_info:
            return standard_response(MESSAGES['error']['invalid_request'], status=400)

        try:
            project_info_json = json.loads(project_info)
            project_id = project_info_json.get('project_id')
            if not project_id:
                return standard_response("프로젝트 ID가 필요합니다", status=400)
                
            project = db.projects.find_one({'_id': ObjectId(project_id)})
            if not project:
                return standard_response("프로젝트를 찾을 수 없습니다", status=400)
            
        except json.JSONDecodeError:
            return standard_response("잘못된 프로젝트 정보 형식입니다", status=400)

        uploaded_files = []
        uploaded_image_ids = []  # MongoDB에 저장된 이미지 ID 목록

        for file in files:
            if file and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    continue

                filename = secure_filename(file.filename)
                base_path = os.path.abspath(f"./mnt/{project_id}/analysis")
                file_path = os.path.join(base_path, "source", filename)
                thumbnail_path = os.path.join(base_path, "thumbnail", f"thum_{filename}")
                
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                file.save(file_path)
                
                if create_thumbnail(file_path, thumbnail_path):
                    # DB에 이미지 정보 저장
                    image_doc = {
                        'FileName': filename,
                        'FilePath': file_path,
                        'OriginalFileName': filename,
                        'ThumnailPath': thumbnail_path,
                        'ProjectInfo': {
                            'ProjectName': project['project_name'],
                            'ID': str(project['_id'])
                        },
                        'AnalysisFolder': 'analysis',
                        'uploadState': 'uploaded',
                        'AI_processed': False,
                        'exif_parsed': False,
                        'UploadDate': datetime.utcnow()
                    }
                    
                    result = db.images.insert_one(image_doc)
                    image_id = str(result.inserted_id)
                    uploaded_image_ids.append(image_id)
                    
                    uploaded_files.append({
                        'filename': filename,
                        'path': file_path,
                        'thumbnail': thumbnail_path,
                        'project_id': project_id,
                        'image_id': image_id
                    })

        if uploaded_files:
            return standard_response(
                MESSAGES['success']['upload'],
                data={
                    'uploaded_files': uploaded_files,
                    'image_ids': uploaded_image_ids
                }
            )

        return standard_response(MESSAGES['error']['invalid_request'], status=400)

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return handle_exception(e)


@upload_bp.route('/files/bulk-delete', methods=['DELETE'])
@jwt_required()
def delete_multiple_files():
    """다중 파일 삭제 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        
        if not image_ids:
            return standard_response("삭제할 이미지 ID가 필요합니다", status=400)
        
        deleted_count = 0
        failed_ids = []
        
        for image_id in image_ids:
            try:
                # ObjectId 변환 검증
                try:
                    obj_id = ObjectId(image_id)
                except:
                    failed_ids.append(image_id)
                    continue
                
                # 먼저 이미지 정보만 조회
                image = db.images.find_one({'_id': obj_id})
                
                if not image:
                    failed_ids.append(image_id)
                    continue
                
                # 실제 파일 삭제 시도
                file_deleted = True
                for path in [image.get('FilePath'), image.get('ThumnailPath')]:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except:
                            file_deleted = False
                
                if not file_deleted:
                    failed_ids.append(image_id)
                    continue
                
                # 파일 삭제 성공 시에만 DB에서 삭제
                result = db.images.delete_one({'_id': obj_id})
                if result.deleted_count > 0:
                    deleted_count += 1
                else:
                    failed_ids.append(image_id)
                    
            except:
                failed_ids.append(image_id)
                continue
        
        response_message = f"{deleted_count}개의 파일이 삭제되었습니다."
        if failed_ids:
            response_message += f" {len(failed_ids)}개의 파일 삭제 실패."
        
        # 상태 코드 결정
        status_code = 200  # 기본값: 전체 성공
        if len(failed_ids) == len(image_ids):
            status_code = 500  # 전체 실패
        elif failed_ids:
            status_code = 207  # 부분 성공
            
        return standard_response(
            message=response_message,
            status=status_code,
            data={
                'deleted_count': deleted_count,
                'failed_ids': failed_ids
            }
        )

    except Exception as e:
        logger.error(f"Bulk deletion error: {str(e)}")
        return handle_exception(e)

@upload_bp.route('/files/parse-exif', methods=['POST'])
@jwt_required()
def parse_files():
    """업로드된 파일 EXIF 파싱 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        timeout = data.get('timeout', 30)  # 기본 타임아웃 30초
        
        if not image_ids:
            return standard_response(
                "파싱할 이미지 ID가 필요합니다", 
                status=400
            )
        
        # 해당 이미지들 조회
        images = list(db.images.find({
            '_id': {'$in': [ObjectId(id) for id in image_ids]}
        }))
        
        if not images:
            return standard_response(
                "파싱할 이미지를 찾을 수 없습니다",
                data={'parsed_count': 0}
            )

        # EXIF 파싱 실행 (타임아웃 추가)
        image_paths = [img['FilePath'] for img in images]
        project_info = {
            'name': images[0]['ProjectInfo']['ProjectName'],
            'id': images[0]['ProjectInfo']['ID']
        }
        
        try:
            processed_images = process_images(
                image_paths,
                project_info,
                'analysis',
                str(datetime.utcnow()),
                timeout=timeout  # 타임아웃 설정 추가
            )
        except TimeoutError:
            return standard_response(
                "EXIF 파싱 시간이 초과되었습니다",
                status=408,  # Request Timeout
                data={
                    'timeout': timeout,
                    'image_count': len(images)
                }
            )
        
        # 파싱 결과 DB 업데이트
        update_count = 0
        parsed_images = []
        for processed in processed_images:
            result = db.images.update_one(
                {'FilePath': processed['FilePath']},
                {
                    '$set': {
                        'SerialNumber': processed['SerialNumber'],
                        'DateTimeOriginal': processed['DateTimeOriginal'],
                        'UserLabel': processed.get('UserLabel', 'UNKNOWN'),
                        'serial_filename': processed['serial_filename'],
                        'evtnum': processed.get('evtnum'),
                        'exif_parsed': True,
                        'exif_parsed_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    }
                }
            )
            if result.modified_count > 0:
                update_count += 1
                parsed_images.append({
                    'image_id': str(processed['_id']),  # 이미지 ID 추가
                    'filename': processed['FileName'],
                    'serial_number': processed['SerialNumber'],
                    'datetime': processed['DateTimeOriginal']['$date'],
                    'evtnum': processed.get('evtnum')
                })
        
        return standard_response(
            "EXIF 파싱이 완료되었습니다",
            data={
                'total_images': len(images),
                'parsed_count': update_count,
                'parsed_images': parsed_images
            }
        )
        
    except Exception as e:
        logger.error(f"EXIF parsing error: {str(e)}")
        return handle_exception(e)

