from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
from .exifparser import process_images
from pymongo import MongoClient

upload = Blueprint('upload', __name__)

# MongoDB 연결 설정
client = MongoClient('mongodb://localhost:27017/')
db = client['your_database_name']
images_collection = db['images']

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    """허용된 파일 확장자 검사"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@upload.route('/upload', methods=['POST'])
def upload_files():
    try:
        # 프로젝트 정보와 분석 폴더 정보 가져오기
        project_info = request.form.get('project_info')
        analysis_folder = request.form.get('analysis_folder')
        session_id = request.form.get('session_id')

        if 'files' not in request.files:
            return jsonify({'error': '파일이 없습니다'}), 400

        files = request.files.getlist('files')
        
        # 임시 저장 경로 생성
        temp_paths = []
        base_path = f"./mnt/{project_info['_id']}/{analysis_folder}/source"
        os.makedirs(base_path, exist_ok=True)
        
        # 파일 임시 저장
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                temp_path = os.path.join(base_path, filename)
                file.save(temp_path)
                temp_paths.append(temp_path)

        # EXIF 데이터 처리 및 MongoDB 저장
        processed_images = process_images(temp_paths, project_info, analysis_folder, session_id)
        
        if processed_images:
            # MongoDB에 저장
            images_collection.insert_many(processed_images)
            
            return jsonify({
                'message': '파일 업로드 성공',
                'uploaded_count': len(processed_images)
            }), 200
        else:
            return jsonify({'error': '이미지 처리 중 오류 발생'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
