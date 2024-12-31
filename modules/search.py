from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
from pymongo import DESCENDING
from .database import db

search_bp = Blueprint('search', __name__)

@search_bp.route('/search', methods=['GET'])
@jwt_required()
def search_images():
    """이미지 검색 API"""
    try:
        # 검색 파라미터
        search_params = {
            # 기본 검색 조건
            'best_class': request.args.get('species'),
            'best_probability': request.args.get('confidence'),
            'project_name': request.args.get('project'),
            
            # 날짜 범위
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to'),
            
            # EXIF 데이터 기반 검색
            'camera_model': request.args.get('camera_model'),
            'serial_number': request.args.get('serial_number'),
            'user_label': request.args.get('user_label'),
            
            # 페이지네이션
            'page': int(request.args.get('page', 1)),
            'per_page': int(request.args.get('per_page', 50))
        }
        
        result = search_images_db(search_params)
        
        if 'error' in result:
            return jsonify({'message': 'Failed to search images', 'error': result['error']}), 500
            
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'message': 'Search error', 'error': str(e)}), 400

def search_images_db(params):
    """
    이미지 검색 함수
    """
    try:
        query = {}
        
        # 1. 종 분류 검색
        if params.get('best_class'):
            query['BestClass'] = {'$regex': params['best_class'], '$options': 'i'}
            
        # 2. 신뢰도 검색
        if params.get('best_probability'):
            min_prob = float(params['best_probability'])
            query['Infos.best_probability'] = {'$gte': min_prob}
            
        # 3. 프로젝트 검색
        if params.get('project_name'):
            query['ProjectInfo.ProjectName'] = {'$regex': params['project_name'], '$options': 'i'}
            
        # 4. 날짜 범위 검색
        date_query = {}
        if params.get('date_from'):
            date_query['$gte'] = datetime.fromisoformat(params['date_from'])
        if params.get('date_to'):
            date_query['$lte'] = datetime.fromisoformat(params['date_to'])
        if date_query:
            query['DateTimeOriginal'] = date_query
            
        # 5. EXIF 데이터 검색
        if params.get('camera_model'):
            query['UserLabel'] = {'$regex': params['camera_model'], '$options': 'i'}
        if params.get('serial_number'):
            query['SerialNumber'] = params['serial_number']
        if params.get('user_label'):
            query['UserLabel'] = {'$regex': params['user_label'], '$options': 'i'}

        # 페이지네이션
        skip = (params['page'] - 1) * params['per_page']
        
        # 검색 실행
        total = db.images.count_documents(query)
        cursor = db.images.find(query).sort('DateTimeOriginal', DESCENDING) \
                         .skip(skip).limit(params['per_page'])
        
        # ObjectId를 문자열로 변환
        images = []
        for img in cursor:
            img['_id'] = str(img['_id'])
            images.append(img)
            
        return {
            'images': images,
            'total': total,
            'page': params['page'],
            'per_page': params['per_page'],
            'total_pages': (total + params['per_page'] - 1) // params['per_page']
        }
        
    except Exception as e:
        return {'error': str(e)} 