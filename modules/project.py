from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from bson import ObjectId
from typing import Tuple, Dict, Any, List
import json
from .database import db
from .utils.response import standard_response, handle_exception, pagination_meta
from .utils.constants import MESSAGES, PROJECT_STATUSES, PER_PAGE_DEFAULT

project_bp = Blueprint('project', __name__)

@project_bp.route('/project', methods=['GET'])
@jwt_required()
def get_projects() -> Tuple[Dict[str, Any], int]:
    """프로젝트 목록 조회 API"""
    try:
        status = request.args.get('status')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))
        
        query: Dict[str, Any] = {}
        if status:
            query['status'] = status
            
        total = db.projects.count_documents(query)
        projects: List[Dict[str, Any]] = list(db.projects.find(query)
                       .sort('created_at', -1)
                       .skip((page - 1) * per_page)
                       .limit(per_page))
                       
        for project in projects:
            project['_id'] = str(project['_id'])
            
        return standard_response(
            "프로젝트 목록 조회 성공",
            data={'projects': projects},
            meta=pagination_meta(total, page, per_page)
        )
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@project_bp.route('/project/check-name', methods=['GET'])
@jwt_required()
def check_project_name():
    """프로젝트 이름 중복 확인 API"""
    try:
        project_name = request.args.get('name')
        if not project_name:
            return handle_exception(
                Exception("프로젝트 이름이 필요합니다"),
                error_type="validation_error"
            )

        exists = db.projects.find_one({'project_name': project_name}) is not None
        return standard_response(
            "프로젝트 이름 중복 확인 완료",
            data={'exists': exists}
        )

    except Exception as e:
        return handle_exception(e, error_type="db_error")

@project_bp.route('/project', methods=['POST'])
@jwt_required()
def create_project() -> Tuple[Dict[str, Any], int]:
    """프로젝트 생성 API"""
    try:
        data = request.get_json()
        project_name = data.get('project_name')
        description = data.get('description', '')
        
        if not project_name:
            return handle_exception(
                Exception(MESSAGES['error']['invalid_request']),
                error_type="validation_error"
            )
            
        if db.projects.find_one({'project_name': project_name}):
            return handle_exception(
                Exception("이미 존재하는 프로젝트명입니다"),
                error_type="validation_error"
            )
            
        project: Dict[str, Any] = {
            'project_name': project_name,
            'description': description,
            'status': '준비 중',
            'created_at': datetime.utcnow(),
            'created_by': get_jwt_identity(),
            'updated_at': datetime.utcnow()
        }
        
        result = db.projects.insert_one(project)
        project['_id'] = str(result.inserted_id)
        
        return standard_response("프로젝트 생성 성공", data=project)
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@project_bp.route('/project/<project_id>', methods=['PUT'])
@jwt_required()
def update_project(project_id: str) -> Tuple[Dict[str, Any], int]:
    """프로젝트 수정 API"""
    try:
        data = request.get_json()
        status = data.get('status')
        description = data.get('description')
        
        update_data: Dict[str, Any] = {'updated_at': datetime.utcnow()}
        if status and status in PROJECT_STATUSES:
            update_data['status'] = status
        if description is not None:
            update_data['description'] = description
            
        result = db.projects.update_one(
            {'_id': ObjectId(project_id)},
            {'$set': update_data}
        )
        
        if result.modified_count == 0:
            return handle_exception(
                Exception(MESSAGES['error']['not_found']),
                error_type="validation_error"
            )
            
        return standard_response("프로젝트가 수정되었습니다")
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@project_bp.route('/project/<project_id>', methods=['DELETE'])
@jwt_required()
def delete_project(project_id: str) -> Tuple[Dict[str, Any], int]:
    """프로젝트 삭제 API"""
    try:
        result = db.projects.delete_one({'_id': ObjectId(project_id)})
        
        if result.deleted_count == 0:
            return handle_exception(
                Exception(MESSAGES['error']['not_found']),
                error_type="validation_error"
            )
            
        # 관련된 이미지들도 삭제
        db.images.delete_many({'ProjectInfo.ProjectName': project_id})
        
        return standard_response("프로젝트가 삭제되었습니다")
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")
