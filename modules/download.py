from flask import Blueprint, send_file, jsonify, request
from flask_jwt_extended import jwt_required
from bson import ObjectId
from .database import db
import os
import zipfile
import io

download_bp = Blueprint('download', __name__)

@download_bp.route('/download/single/<image_id>', methods=['GET'])
@jwt_required()
def download_single_image(image_id):
    """단일 이미지 다운로드"""
    try:
        # ObjectId로 변환
        object_id = ObjectId(image_id)
        
        # 이미지 정보 조회
        image = db.images.find_one({'_id': object_id})
        if not image:
            return jsonify({'message': 'Image not found'}), 404
            
        file_path = image.get('FilePath')
        if not os.path.exists(file_path):
            return jsonify({'message': 'Image file not found'}), 404
            
        return send_file(
            file_path,
            as_attachment=True,
            download_name=image.get('FileName')  # FileName 사용
        )
        
    except Exception as e:
        return jsonify({'message': 'Download failed', 'error': str(e)}), 400

@download_bp.route('/download/multiple', methods=['POST'])
@jwt_required()
def download_multiple_images():
    """여러 이미지 ZIP 다운로드"""
    try:
        image_ids = request.json.get('image_ids', [])
        if not image_ids:
            return jsonify({'message': 'No images selected'}), 400
            
        # ZIP 파일 생성
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            for img_id in image_ids:
                image = db.images.find_one({'_id': ObjectId(img_id)})
                if image and os.path.exists(image.get('FilePath')):
                    # FileName을 ZIP 내부 파일명으로 사용
                    zf.write(
                        image['FilePath'], 
                        image['FileName']  # FileName 사용
                    )
                    
        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name='images.zip'
        )
        
    except Exception as e:
        return jsonify({'message': 'Download failed', 'error': str(e)}), 400 