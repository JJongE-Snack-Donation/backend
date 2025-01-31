from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from bson import ObjectId
from typing import Tuple, Dict, Any, List
import os
import shutil

from .database import db
from .utils.response import standard_response, handle_exception
from .utils.constants import MESSAGES

image_move_bp = Blueprint('image_move', __name__)

@image_move_bp.route('/move/images', methods=['POST'])
@jwt_required()
def move_images() -> Tuple[Dict[str, Any], int]:
    """이미지 이동 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        target_project_id = data.get('target_project_id')
        target_folder = data.get('target_folder')
        
        if not image_ids or not target_project_id or not target_folder:
            return handle_exception(
                Exception("필수 파라미터가 누락되었습니다"),
                error_type="validation_error"
            )
            
        # 대상 프로젝트 확인
        target_project = db.projects.find_one({'_id': ObjectId(target_project_id)})
        if not target_project:
            return handle_exception(
                Exception("대상 프로젝트를 찾을 수 없습니다"),
                error_type="validation_error"
            )
            
        moved_count = 0
        failed_moves: List[Dict[str, Any]] = []
        
        for image_id in image_ids:
            try:
                image = db.images.find_one({'_id': ObjectId(image_id)})
                if not image:
                    failed_moves.append({
                        'image_id': image_id,
                        'reason': '이미지를 찾을 수 없습니다'
                    })
                    continue
                    
                # 파일 이동 처리
                old_path = image['FilePath']
                new_path = f"./mnt/{target_project_id}/{target_folder}/source/{os.path.basename(old_path)}"
                
                # 썸네일 경로도 업데이트
                old_thumb = image['ThumnailPath']
                new_thumb = f"./mnt/{target_project_id}/{target_folder}/thumbnail/thum_{os.path.basename(old_path)}"
                
                # 물리적 파일 이동
                if os.path.exists(old_path):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    shutil.move(old_path, new_path)
                    
                if os.path.exists(old_thumb):
                    os.makedirs(os.path.dirname(new_thumb), exist_ok=True)
                    shutil.move(old_thumb, new_thumb)
                
                # DB 업데이트
                db.images.update_one(
                    {'_id': ObjectId(image_id)},
                    {
                        '$set': {
                            'FilePath': new_path,
                            'ThumnailPath': new_thumb,
                            'ProjectInfo.ProjectName': target_project['project_name'],
                            'ProjectInfo.ID': str(target_project['_id']),
                            'AnalysisFolder': target_folder
                        }
                    }
                )
                
                moved_count += 1
                
            except Exception as e:
                failed_moves.append({
                    'image_id': image_id,
                    'reason': str(e)
                })
        
        return standard_response(
            f"{moved_count}개의 이미지가 이동되었습니다",
            data={
                'moved_count': moved_count,
                'failed_moves': failed_moves
            }
        )
        
    except Exception as e:
        return handle_exception(e, error_type="file_error") 