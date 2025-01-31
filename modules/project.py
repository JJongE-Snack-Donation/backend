from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from bson import ObjectId
from .database import db  # 가정: MongoDB를 사용하는 경우

project_bp = Blueprint('project', __name__)

@project_bp.route('/project', methods=['GET'])
@jwt_required()
def get_projects():
    """
    프로젝트 목록 조회 API
    query parameters:
    - status: 프로젝트 상태 (준비 중/준비 완료)
    - page: 페이지 번호
    - per_page: 페이지당 프로젝트 수
    """
    try:
        status = request.args.get('status')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        query = {}
        if status:
            query['status'] = status

        total = db.projects.count_documents(query)
        projects = list(db.projects.find(query)
                        .sort('created_at', -1)
                        .skip((page - 1) * per_page)
                        .limit(per_page))

        for project in projects:
            project['_id'] = str(project['_id'])

        return jsonify({
            'status': 200,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
            'projects': projects
        }), 200

    except Exception as e:
        return jsonify({
            'status': 500,
            'message': f'서버 오류: {str(e)}'
        }), 500


@project_bp.route('/project/check-name', methods=['GET'])
@jwt_required()
def check_project_name():
    """프로젝트 이름 중복 확인 API"""
    try:
        project_name = request.args.get('name')
        if not project_name:
            return jsonify({
                'status': 400,
                'message': '프로젝트 이름이 필요합니다'
            }), 400

        exists = db.projects.find_one({'project_name': project_name}) is not None
        return jsonify({
            'status': 200,
            'exists': exists
        }), 200

    except Exception as e:
        return jsonify({
            'status': 500,
            'message': f'서버 오류: {str(e)}'
        }), 500


@project_bp.route('/project', methods=['POST'])
@jwt_required()
def create_project():
    """
    새 프로젝트 생성 API
    Request Body:
    {
        "project_name": "프로젝트명",
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD",
        "address": "주소",
        "organization": "소속기관",  # 선택
        "memo": "메모"              # 선택
    }
    """
    try:
        data = request.get_json()

        # 필수 필드 검증
        required_fields = ['project_name', 'start_date', 'end_date', 'address']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'status': 400,
                    'message': f'필수 필드 누락: {field}'
                }), 400

        # 현재 로그인한 사용자 정보 가져오기
        current_user = get_jwt_identity()
        user = db.users.find_one({'username': current_user})

        # 프로젝트 데이터 구성
        project_data = {
            'project_name': data['project_name'],
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'address': data['address'],
            'organization': data.get('organization', ''),
            'memo': data.get('memo', ''),
            'status': '준비 중',
            'manager_username': current_user,
            'manager_email': user['email'],
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        result = db.projects.insert_one(project_data)

        return jsonify({
            'status': 200,
            'message': '프로젝트가 생성되었습니다',
            'project_id': str(result.inserted_id)
        }), 200

    except Exception as e:
        return jsonify({
            'status': 500,
            'message': f'서버 오류: {str(e)}'
        }), 500


@project_bp.route('/project/<project_id>', methods=['PUT'])
@jwt_required()
def update_project(project_id):
    """
    프로젝트 수정 API
    Request Body: (모든 필드 선택적)
    {
        "project_name": "수정된 프로젝트명",
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD",
        "address": "수정된 주소",
        "organization": "수정된 소속기관",
        "memo": "수정된 메모",
        "status": "준비 완료"
    }
    """
    try:
        data = request.get_json()

        # 수정 가능한 필드 목록
        allowed_fields = {
            'project_name', 'start_date', 'end_date', 'address',
            'organization', 'memo', 'status'
        }

        # 업데이트할 데이터 구성
        update_data = {
            k: v for k, v in data.items()
            if k in allowed_fields and v is not None
        }

        if not update_data:
            return jsonify({
                'status': 400,
                'message': '수정할 내용이 없습니다'
            }), 400

        result = db.projects.update_one(
            {'_id': ObjectId(project_id)},
            {'$set': update_data}
        )

        if result.modified_count == 0:
            return jsonify({
                'status': 404,
                'message': '프로젝트를 찾을 수 없습니다'
            }), 404

        return jsonify({
            'status': 200,
            'message': '프로젝트가 수정되었습니다'
        }), 200

    except Exception as e:
        return jsonify({
            'status': 500,
            'message': f'서버 오류: {str(e)}'
        }), 500


@project_bp.route('/project/<project_id>', methods=['DELETE'])
@jwt_required()
def delete_project(project_id):
    """프로젝트 삭제 API"""
    try:
        result = db.projects.delete_one({'_id': ObjectId(project_id)})

        if result.deleted_count == 0:
            return jsonify({
                'status': 404,
                'message': '프로젝트를 찾을 수 없습니다'
            }), 404

        # 관련된 이미지들도 삭제
        db.images.delete_many({'ProjectInfo.ProjectName': project_id})

        return jsonify({
            'status': 200,
            'message': '프로젝트가 삭제되었습니다'
        }), 200

    except Exception as e:
        return jsonify({
            'status': 500,
            'message': f'서버 오류: {str(e)}'
        }), 500
