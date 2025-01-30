from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
import logging
from .exifparser import process_images
from pymongo import MongoClient
from PIL import Image
from flask_jwt_extended import jwt_required

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__)

# MongoDB 연결 설정
try:
    client = MongoClient('mongodb://localhost:27017/')
    db = client['your_database_name']
    images_collection = db['images']
except Exception as e:
    logger.error(f"MongoDB connection error: {str(e)}")

ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}
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

@upload_bp.route('/files/upload', methods=['POST'])
@jwt_required()
def upload_files():
    """파일 업로드 API"""
    try:
        if 'files[]' not in request.files:
            return jsonify({
                "status": 400,
                "message": "파일이 없습니다"
            }), 400

        files = request.files.getlist('files[]')
        uploaded_files = []
        
        for file in files:
            if file and allowed_file(file.filename):
                if len(file.read()) > MAX_FILE_SIZE:
                    return jsonify({
                        "status": 400,
                        "message": f"파일 크기 초과: {file.filename}"
                    }), 400
                    
                file.seek(0)
                filename = secure_filename(file.filename)
                
                # 파일 저장 및 처리 로직
                file_data = process_file(file, filename)
                if file_data:
                    uploaded_files.append(file_data)
                    
        if uploaded_files:
            # MongoDB에 저장
            result = images_collection.insert_many(uploaded_files)
            
            return jsonify({
                "status": 201,
                "message": "파일 업로드 성공",
                "uploadedFiles": [{
                    "fileId": str(id),
                    "fileName": file['FileName']
                } for id, file in zip(result.inserted_ids, uploaded_files)]
            }), 201
            
        return jsonify({
            "status": 400,
            "message": "유효한 파일이 없습니다"
        }), 400
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({
            "status": 400,
            "message": "파일 업로드 실패"
        }), 400

def process_file(file, filename):
    """파일 처리 및 메타데이터 생성"""
    try:
        # 여기에 파일 처리 로직 구현
        # (process_images 함수 호출 등)
        return {
            'FileName': filename,
            'is_classified': False,
            # 기타 필요한 메타데이터
        }
    except Exception as e:
        logger.error(f"File processing error: {str(e)}")
        return None

# 에러 핸들러
@upload_bp.errorhandler(Exception)
def handle_error(error):
    logger.error(f"Unexpected error: {str(error)}")
    return jsonify({'error': '서버 오류가 발생했습니다'}), 500
