from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime
from .database import db

search_bp = Blueprint('search', __name__)

@search_bp.route('/images/search', methods=['GET'])
@jwt_required()
def search_images():
    """종분류 이미지 검색 API"""
    try:
        # 검색 파라미터
        date = request.args.get('date')
        name = request.args.get('name')
        tag = request.args.get('tag')
        location = request.args.get('location')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # 쿼리 생성
        query = {'is_classified': True}
        
        if date:
            try:
                search_date = datetime.strptime(date, '%Y-%m-%d')
                query['DateTimeOriginal'] = {
                    '$gte': search_date,
                    '$lt': datetime(search_date.year, search_date.month, search_date.day + 1)
                }
            except ValueError:
                return jsonify({
                    "status": 400,
                    "message": "잘못된 날짜 형식"
                }), 400
                
        if name:
            query['FileName'] = {'$regex': name, '$options': 'i'}
            
        if tag:
            query['BestClass'] = {'$regex': tag, '$options': 'i'}
            
        if location:
            query['ProjectInfo.location'] = {'$regex': location, '$options': 'i'}
            
        # 검색 실행
        images = list(db.images.find(
            query,
            {'_id': 1, 'FileName': 1, 'ThumnailPath': 1, 'DateTimeOriginal': 1, 
             'BestClass': 1, 'ProjectInfo': 1}
        ).skip((page - 1) * per_page).limit(per_page))
        
        return jsonify({
            "status": 200,
            "images": [{
                "imageId": str(img['_id']),
                "imageUrl": img['ThumnailPath'],
                "date": img['DateTimeOriginal'].strftime('%Y-%m-%d'),
                "name": img['FileName'],
                "tag": img.get('BestClass', '미확인'),
                "location": img.get('ProjectInfo', {}).get('location', '위치 미상')
            } for img in images]
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500 