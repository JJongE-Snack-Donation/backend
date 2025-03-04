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
        logger.info(f" 요청 헤더: {request.headers}")  # 요청 헤더 확인
        logger.info(f" 요청 폼 데이터: {request.form}")  # 폼 데이터 확인
        logger.info(f" 요청 파일 목록: {request.files}")  # 실제 파일 데이터 확인

        if 'files' not in request.files:
            logger.error(" 'files' 키가 요청에 없음")
            return standard_response(MESSAGES['error']['invalid_request'], status=400)

        files = request.files.getlist('files')
        project_info = request.form.get('project_info')

        logger.info(f" 받은 파일 개수: {len(files)}, 프로젝트 정보: {project_info}")

        if not files or not project_info:
            logger.error(" 파일이 없거나 프로젝트 정보가 없음")
            return standard_response(MESSAGES['error']['invalid_request'], status=400)

        try:
            project_info_json = json.loads(project_info)
            project_id = project_info_json.get('project_id')

            logger.info(f" 프로젝트 ID: {project_id}")

            if not project_id:
                logger.error(" 프로젝트 ID가 없음")
                return standard_response("프로젝트 ID가 필요합니다", status=400)

            project = db.projects.find_one({'_id': ObjectId(project_id)})
            if not project:
                logger.error(f" 프로젝트를 찾을 수 없음: {project_id}")
                return standard_response("프로젝트를 찾을 수 없습니다", status=400)

        except json.JSONDecodeError:
            logger.error(" 프로젝트 정보 JSON 디코딩 실패")
            return standard_response("잘못된 프로젝트 정보 형식입니다", status=400)

        uploaded_files = []
        uploaded_image_ids = []
        skipped_files = []  # 업로드 실패한 파일 목록

        for file in files:
            if file and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    logger.warning(f"파일 크기 초과: {file.filename}")
                    skipped_files.append(file.filename)
                    continue

                filename = secure_filename(file.filename)
                base_path = os.path.abspath(f"./mnt/{project_id}/analysis")
                file_path = os.path.join(base_path, "source", filename)
                thumbnail_path = os.path.join(base_path, "thumbnail", f"thum_{filename}")

                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                file.save(file_path)

                logger.info(f"파일 저장 완료: {file_path}")

                if create_thumbnail(file_path, thumbnail_path):
                    logger.info(f"썸네일 생성 완료: {thumbnail_path}")

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
                        'inspection_complete': False,
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

        logger.info(f"업로드 완료: {len(uploaded_files)}개, 실패: {len(skipped_files)}개")

        if not uploaded_files:
            logger.error("모든 파일 업로드 실패")
            return standard_response("파일 업로드 실패", status=400, data={"skipped_files": skipped_files})

        return standard_response(
            "파일 업로드 완료",
            data={
                'uploaded_files': uploaded_files,
                'image_ids': uploaded_image_ids,
                'skipped_files': skipped_files
            }
        )

    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
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
                    logger.warning(f"Invalid ObjectId format: {image_id}")
                    failed_ids.append(image_id)
                    continue
                
                # 먼저 이미지 정보 조회
                image = db.images.find_one({'_id': obj_id})
                if not image:
                    logger.warning(f"Image not found in DB: {image_id}")
                    failed_ids.append(image_id)
                    continue
                
                # 파일 삭제 시도
                file_deleted = True
                for path in [image.get('FilePath'), image.get('ThumnailPath')]:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                            logger.info(f"File deleted: {path}")
                        except Exception as e:
                            logger.error(f"Failed to delete file {path}: {str(e)}")
                            file_deleted = False
                
                if not file_deleted:
                    failed_ids.append(image_id)
                    continue
                
                # 파일 삭제 성공 시에만 DB에서 삭제
                result = db.images.delete_one({'_id': obj_id})
                if result.deleted_count > 0:
                    deleted_count += 1
                else:
                    logger.warning(f"Failed to delete DB record for: {image_id}")
                    failed_ids.append(image_id)

            except Exception as e:
                logger.error(f"Unexpected error while deleting {image_id}: {str(e)}")
                failed_ids.append(image_id)
                continue

        # 모든 파일 삭제 실패 시 500 응답
        if deleted_count == 0:
            return standard_response(
                "모든 파일 삭제에 실패했습니다",
                status=500,
                data={'deleted_count': 0, 'failed_ids': failed_ids}
            )

        # 일부 삭제 실패 시 206 응답 (Partial Success)
        if failed_ids:
            return standard_response(
                message=f"{deleted_count}개의 파일이 삭제되었습니다. {len(failed_ids)}개의 파일 삭제 실패.",
                status=206,  # Partial Content (부분 성공)
                data={'deleted_count': deleted_count, 'failed_ids': failed_ids}
            )

        # 전체 삭제 성공 시 200 응답
        return standard_response(
            message=f"{deleted_count}개의 파일이 삭제되었습니다",
            status=200,
            data={'deleted_count': deleted_count, 'failed_ids': []}
        )

    except Exception as e:
        logger.error(f"Bulk file delete API error: {str(e)}")
        return standard_response("서버 오류", status=500)

@upload_bp.route('/files/parse-exif', methods=['POST'])
@jwt_required()
def parse_files():
    """업로드된 파일 EXIF 파싱 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        timeout = data.get('timeout', 30)  # 기본 타임아웃 30초

        if not image_ids:
            return standard_response("파싱할 이미지 ID가 필요합니다", status=400)

        images = list(db.images.find({'_id': {'$in': [ObjectId(id) for id in image_ids]}}))
        if not images:
            return standard_response("파싱할 이미지를 찾을 수 없습니다", data={'parsed_count': 0})

        image_paths = [img['FilePath'] for img in images]
        project_info = {
            'name': images[0]['ProjectInfo']['ProjectName'],
            'id': images[0]['ProjectInfo']['ID']
        }

        try:
            processed_images = process_images(image_paths, project_info, 'analysis', str(datetime.utcnow()))
            if not processed_images:
                logger.error("process_images()가 빈 리스트를 반환함")
                return standard_response("EXIF 파싱에 실패했습니다 (process_images 반환값이 비어 있음)", status=500)
        except TimeoutError:
            return standard_response("EXIF 파싱 시간이 초과되었습니다", status=408, data={'timeout': timeout, 'image_count': len(images)})

        update_count = 0
        parsed_images = []
        failed_images = []

        #경로 변환 함수 추가
        def normalize_path(path):
            """Windows와 Linux 경로를 통일하는 함수"""
            if os.name == "nt":  
                path = path.replace("mnt\\", "/mnt/")  # 역슬래시를 슬래시로 변환
            return path.replace("\\", "/")  # 모든 역슬래시를 슬래시로 변경

        for processed in processed_images:
            logger.info(f"🔍 처리된 이미지: {processed}")
            
            # MongoDB에서 찾으려는 파일명과 비교 로그
            existing_doc = db.images.find_one({'OriginalFileName': processed['OriginalFileName']})
            if not existing_doc:
                logger.error(f"MongoDB에서 해당 파일을 찾을 수 없음: {processed['OriginalFileName']}")
            
            result = db.images.update_one(
                {'OriginalFileName': processed['OriginalFileName']},  # 원본 파일명 기반으로 찾기
                {
                    '$set': {
                        'SerialNumber': processed.get('SerialNumber', ''),
                        'DateTimeOriginal': processed.get('DateTimeOriginal', ''),
                        'serial_filename': processed.get('serial_filename', ''),
                        'evtnum': processed.get('evtnum'),
                        'exif_parsed': True,
                        'exif_parsed_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    }
                }
            )

            logger.info(f"MongoDB 업데이트 결과: matched={result.matched_count}, modified={result.modified_count}")

            if result.modified_count > 0:
                update_count += 1
            else:
                failed_images.append(processed.get('FileName', 'Unknown'))

        if failed_images:
            logger.warning(f" EXIF 파싱 실패 이미지 목록: {failed_images}")
            return standard_response("일부 이미지의 EXIF 파싱이 완료되었으나 실패한 파일이 있습니다", status=206, data={'parsed_count': update_count, 'failed_images': failed_images})

        return standard_response("EXIF 파싱이 완료되었습니다", data={'total_images': len(images), 'parsed_count': update_count, 'parsed_images': parsed_images})

    except Exception as e:
        logger.error(f"EXIF parsing error: {str(e)}")
        return handle_exception(e)

