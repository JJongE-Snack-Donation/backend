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
        if exists:
            return standard_response(
                "중복된 프로젝트 이름입니다.",
                data={'exists': True},
                status=409  # 409 Conflict 상태 반환
            )

        return standard_response(
            "프로젝트 이름 사용 가능",
            data={'exists': False}
        )

    except Exception as e:
        return handle_exception(e, error_type="db_error")


@project_bp.route('/project', methods=['POST'])
@jwt_required()
def create_project() -> Tuple[Dict[str, Any], int]:
    """프로젝트 생성 API"""
    try:
        data = request.get_json()
        current_user = get_jwt_identity()

        # 현재 사용자 정보 조회
        user = db.users.find_one({'username': current_user})
        if not user:
            return handle_exception(
                Exception("사용자 정보를 찾을 수 없습니다"),
                error_type="validation_error"
            )

        project_name = data.get('project_name')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        address = data.get('address')
        manager_organization = data.get('manager_organization', '')
        memo = data.get('memo', '')

        # 필수 필드 검증
        required_fields = {
            'project_name': project_name,
            'start_date': start_date,
            'end_date': end_date,
            'address': address
        }
        missing_fields = [field for field, value in required_fields.items() if not value]
        if missing_fields:
            return handle_exception(
                Exception(f"필수 필드가 누락되었습니다: {', '.join(missing_fields)}"),
                error_type="validation_error"
            )

        # 날짜 검증 및 변환
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if end_date < start_date:
                return handle_exception(
                    Exception("종료일이 시작일보다 빠를 수 없습니다"),
                    error_type="validation_error"
                )
        except ValueError:
            return handle_exception(
                Exception("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)"),
                error_type="validation_error"
            )

        if db.projects.find_one({'project_name': project_name}):
            return handle_exception(
                Exception("이미 존재하는 프로젝트명입니다"),
                error_type="validation_error"
            )

        # 현재 시각을 생성 시각으로 사용
        creation_time = datetime.utcnow()

        project: Dict[str, Any] = {
            'project_name': project_name,
            'start_date': start_date,
            'end_date': end_date,
            'address': address,
            'manager_name': user['username'],
            'manager_email': user['email'],
            'manager_organization': manager_organization,
            'memo': memo,
            'status': '준비 완료',  # 프로젝트 상태를 '준비 완료'로 설정
            'progress': 0,
            'created_at': creation_time,
            'created_by': current_user,
            'updated_at': creation_time
        }

        result = db.projects.insert_one(project)
        project['_id'] = str(result.inserted_id)

        # 날짜 및 시간 포맷 변환
        project['start_date'] = start_date.strftime('%Y-%m-%d')
        project['end_date'] = end_date.strftime('%Y-%m-%d')
        project['created_at'] = project['created_at'].isoformat()
        project['updated_at'] = project['updated_at'].isoformat()

        return standard_response("프로젝트 생성 성공", data=project)

    except Exception as e:
        return handle_exception(e, error_type="db_error")




@project_bp.route('/project/<project_id>', methods=['PUT'])
@jwt_required()
def update_project(project_id: str) -> Tuple[Dict[str, Any], int]:
    """프로젝트 수정 API"""
    try:
        print(f"[1] 프로젝트 수정 시작 - 프로젝트 ID: {project_id}")
        data = request.get_json()
        print(f"[2] 요청 데이터: {data}")
        
        current_user = get_jwt_identity()
        print(f"[3] 현재 사용자: {current_user}")

        # 현재 사용자 정보 조회
        user = db.users.find_one({'username': current_user})
        if not user:
            print(f"[ERROR] 사용자를 찾을 수 없음: {current_user}")
            return handle_exception(
                Exception("사용자 정보를 찾을 수 없습니다"),
                error_type="validation_error"
            )
        print(f"[4] 사용자 정보 조회 성공: {user['username']}")
        
        # 요청 데이터와 DB 필드 매핑
        field_mapping = {
            'project_name': 'project_name',
            'start_date': 'start_date',
            'end_date': 'end_date',
            'address': 'address',
            'memo': 'memo'
        }
        
        # 업데이트할 데이터 준비
        update_data: Dict[str, Any] = {
            'updated_at': datetime.utcnow(),
            'manager_username': user['username'],
            'manager_email': user['email']
        }
        print(f"[5] 초기 업데이트 데이터: {update_data}")
        
        # 매핑된 필드명으로 데이터 변환
        for client_field, db_field in field_mapping.items():
            if client_field in data:
                # 날짜 필드 처리
                if client_field in ['start_date', 'end_date'] and data[client_field]:
                    try:
                        update_data[db_field] = datetime.strptime(data[client_field], '%Y-%m-%d')
                        print(f"[6] 날짜 필드 변환 성공 - {client_field}: {data[client_field]}")
                    except ValueError as e:
                        print(f"[ERROR] 날짜 형식 변환 실패 - {client_field}: {data[client_field]}")
                        return handle_exception(
                            Exception("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)"),
                            error_type="validation_error"
                        )
                else:
                    update_data[db_field] = data[client_field]
        
        print(f"[7] 최종 업데이트 데이터: {update_data}")
        
        # 프로젝트 업데이트
        result = db.projects.update_one(
            {'_id': ObjectId(project_id)},
            {'$set': update_data}
        )
        print(f"[8] 업데이트 결과 - modified_count: {result.modified_count}")
        
        if result.modified_count == 0:
            print(f"[ERROR] 프로젝트를 찾을 수 없음 - ID: {project_id}")
            return handle_exception(
                Exception(MESSAGES['error']['not_found']),
                error_type="validation_error"
            )
            
        # 업데이트된 프로젝트 정보 조회
        updated_project = db.projects.find_one({'_id': ObjectId(project_id)})
        if not updated_project:
            print(f"[ERROR] 업데이트된 프로젝트 조회 실패 - ID: {project_id}")
            return handle_exception(
                Exception("프로젝트 정보를 찾을 수 없습니다"),
                error_type="db_error"
            )
        print(f"[9] 업데이트된 프로젝트 조회 성공")
            
        # ObjectId를 문자열로 변환
        updated_project['_id'] = str(updated_project['_id'])
        
        # datetime 객체를 문자열로 변환
        for date_field in ['start_date', 'end_date', 'created_at', 'updated_at']:
            if date_field in updated_project and updated_project[date_field]:
                updated_project[date_field] = updated_project[date_field].isoformat()
        
        print(f"[10] 응답 데이터 준비 완료")
        return standard_response(
            "프로젝트가 수정되었습니다",
            data={'project': updated_project}
        )
        
    except Exception as e:
        print(f"[ERROR] 예외 발생: {str(e)}")
        print(f"[ERROR] 예외 타입: {type(e)}")
        import traceback
        print(f"[ERROR] 스택 트레이스:\n{traceback.format_exc()}")
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
