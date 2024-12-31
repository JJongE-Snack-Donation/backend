from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
import logging
from .exifparser import process_images
from pymongo import MongoClient
from PIL import Image

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

upload = Blueprint('upload', __name__)

# MongoDB 연결 설정
try:
    client = MongoClient('mongodb://localhost:27017/')
    db = client['your_database_name']
    images_collection = db['images']
except Exception as e:
    logger.error(f"MongoDB connection error: {str(e)}")

ALLOWED_EXTENSIONS = {'jpg'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
THUMBNAIL_SIZE = (200, 200)

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

@upload.route('/upload', methods=['POST'])
def upload_files():
    """파일 업로드 처리 엔드포인트"""
    try:
        # 요청 데이터 검증
        if 'files' not in request.files:
            return jsonify({'error': '파일이 없습니다'}), 400

        project_info = request.form.get('project_info')
        analysis_folder = request.form.get('analysis_folder')
        session_id = request.form.get('session_id')

        if not all([project_info, analysis_folder, session_id]):
            return jsonify({'error': '필수 정보가 누락되었습니다'}), 400

        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': '업로드할 파일이 없습니다'}), 400

        # 임시 저장 경로 생성
        temp_paths = []
        base_path = f"./mnt/{project_info['_id']}/{analysis_folder}/source"
        os.makedirs(base_path, exist_ok=True)
        
        # 파일 저장 및 검증
        for file in files:
            if file and allowed_file(file.filename):
                if len(file.read()) > MAX_FILE_SIZE:
                    return jsonify({'error': f'파일 크기가 너무 큽니다: {file.filename}'}), 400
                file.seek(0)  # 파일 포인터 리셋
                
                filename = secure_filename(file.filename)
                temp_path = os.path.join(base_path, filename)
                file.save(temp_path)
                temp_paths.append(temp_path)
            else:
                return jsonify({'error': f'허용되지 않는 파일 형식입니다: {file.filename}'}), 400

        # EXIF 데이터 처리
        processed_images = process_images(temp_paths, project_info, analysis_folder, session_id)
        
        if not processed_images:
            return jsonify({'error': '이미지 처리 중 오류가 발생했습니다'}), 500

        # 기본적으로 미분류 상태로 설정
        for img_data in processed_images:
            img_data['is_classified'] = False
            
        # MongoDB에 저장
        try:
            result = images_collection.insert_many(processed_images)
            return jsonify({
                'message': '파일 업로드 성공',
                'uploaded_count': len(processed_images),
                'image_ids': [str(id) for id in result.inserted_ids]
            }), 200
        except Exception as e:
            logger.error(f"MongoDB insertion error: {str(e)}")
            return jsonify({'error': 'DB 저장 중 오류가 발생했습니다'}), 500

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 에러 핸들러
@upload.errorhandler(Exception)
def handle_error(error):
    logger.error(f"Unexpected error: {str(error)}")
    return jsonify({'error': '서버 오류가 발생했습니다'}), 500
