from flask import Blueprint, send_file, request, current_app
from flask_jwt_extended import jwt_required
from bson import ObjectId
from typing import Tuple, Dict, Any, Union
import os
import zipfile
import io

from .database import db
from .utils.response import standard_response, handle_exception
from .utils.constants import MESSAGES

download_bp = Blueprint('download', __name__)

@download_bp.route('/download/image/<image_id>', methods=['GET'])
@jwt_required()
def download_image(image_id: str):
    """단일 이미지 다운로드 API"""
    try:
        image = db.images.find_one({'_id': ObjectId(image_id)})
        if not image:
            return handle_exception(Exception(MESSAGES['error']['not_found']), error_type="validation_error")
        
        relative_path = image.get('FilePath')
        if not relative_path:
            return handle_exception(Exception("파일 경로 정보가 없습니다"), error_type="file_error")
        
        # 상대 경로를 절대 경로로 변환
        if relative_path.startswith('./'):
            relative_path = relative_path[2:]  # './' 제거
        
        # 애플리케이션의 루트 디렉토리를 기준으로 절대 경로 생성
        file_path = os.path.join(current_app.root_path, relative_path)
        
        if not os.path.isfile(file_path):
            return handle_exception(Exception(f"파일을 찾을 수 없습니다: {file_path}"), error_type="file_error")
        
        file_name = os.path.basename(file_path)
        
        return send_file(file_path, as_attachment=True, download_name=file_name)
    
    except Exception as e:
        return handle_exception(e, error_type="file_error")



@download_bp.route('/download/images', methods=['POST'])
@jwt_required()
def download_multiple_images() -> Union[Tuple[Dict[str, Any], int], Any]:
    """다중 이미지 다운로드 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        
        if not image_ids:
            return handle_exception(
                Exception("다운로드할 이미지를 선택해주세요"),
                error_type="validation_error"
            )

        # ZIP 파일 생성
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            for image_id in image_ids:
                image = db.images.find_one({'_id': ObjectId(image_id)})
                if not image:
                    continue
                    
                relative_path = image.get('FilePath')
                if not relative_path:
                    continue

                # 상대 경로를 절대 경로로 변환
                if relative_path.startswith('./'):
                    relative_path = relative_path[2:]  # './' 제거
                
                # 애플리케이션의 루트 디렉토리를 기준으로 절대 경로 생성
                file_path = os.path.join(current_app.root_path, relative_path)
                
                if not os.path.isfile(file_path):
                    continue
                    
                # ZIP 파일에 이미지 추가
                zf.write(
                    file_path, 
                    arcname=image.get('FileName', f'image_{image_id}.jpg')
                )
                
        memory_file.seek(0)
        
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name='images.zip'
        )
        
    except Exception as e:
        return handle_exception(e, error_type="file_error")
