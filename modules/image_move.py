from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from bson import ObjectId
from .database import db

image_move_bp = Blueprint('image_move', __name__)

@image_move_bp.route('/images/move', methods=['POST'])
@jwt_required()
def move_image_classification():
    """이미지 분류 상태 변경 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        to_classified = data.get('to_classified', True)
        
        if not image_ids:
            return jsonify({'message': 'No images selected'}), 400
            
        try:
            object_ids = [ObjectId(id) for id in image_ids]
        except:
            return jsonify({'message': 'Invalid image ID format'}), 400
            
        result = update_image_classification(object_ids, to_classified)
        
        if result.get('error'):
            return jsonify({'message': 'Failed to move images', 'error': result['error']}), 500
            
        # 업데이트된 이미지 정보 조회
        updated_images = get_updated_images(object_ids, to_classified)
        
        return jsonify({
            'message': 'Images moved successfully',
            'moved_count': result.get('modified_count', 0),
            'images': updated_images
        }), 200
        
    except Exception as e:
        return jsonify({'message': 'Error moving images', 'error': str(e)}), 400

def update_image_classification(image_ids, to_classified):
    """이미지 분류 상태 업데이트"""
    try:
        result = db.images.update_many(
            {'_id': {'$in': image_ids}},
            {'$set': {'is_classified': to_classified}}
        )
        
        return {
            'modified_count': result.modified_count
        }
    except Exception as e:
        return {'error': str(e)}

def get_updated_images(image_ids, is_classified):
    """
    업데이트된 이미지 정보 조회
    분류/미분류 상태에 따라 다른 필드 반환
    """
    try:
        images = []
        cursor = db.images.find({'_id': {'$in': image_ids}})
        
        for img in cursor:
            if is_classified:
                # 분류된 이미지 데이터 구조
                image_data = {
                    # TODO: 딥러닝 분석 결과 필드 (추후 구현)
                    # 'Infos': [{
                    #     'best_class': info.get('best_class'),
                    #     'best_probability': info.get('best_probability'),
                    #     'name': info.get('name'),
                    #     'bbox': info.get('bbox'),
                    #     'new_bbox': info.get('new_bbox')
                    # } for info in img.get('Infos', [])],
                    # 'size': img.get('size'),
                    # 'Count': img.get('Count'),
                    # 'BestClass': img.get('BestClass'),
                    # 'evtdate': img.get('evtdate'),
                    # 'evtnum': img.get('evtnum'),
                    'ImageDatas': {
                        '_id': str(img['_id']),
                        'FileName': img.get('FileName'),
                        'FilePath': img.get('FilePath'),
                        'OriginalFileName': img.get('OriginalFileName'),
                        'ThumnailPath': img.get('ThumnailPath'),
                        'SerialNumber': img.get('SerialNumber'),
                        'UserLabel': img.get('UserLabel'),
                        'DateTimeOriginal': img.get('DateTimeOriginal'),
                        'ProjectInfo': img.get('ProjectInfo'),
                        'AnalysisFolder': img.get('AnalysisFolder'),
                        'sessionid': img.get('sessionid'),
                        'uploadState': img.get('uploadState'),
                        'serial_filename': img.get('serial_filename')
                    }
                }
            else:
                # 미분류 이미지 데이터 구조
                image_data = {
                    'FileName': img.get('FileName'),
                    'FilePath': img.get('FilePath'),
                    'OriginalFileName': img.get('OriginalFileName'),
                    'ThumnailPath': img.get('ThumnailPath'),
                    'SerialNumber': img.get('SerialNumber'),
                    'UserLabel': img.get('UserLabel'),
                    'DateTimeOriginal': img.get('DateTimeOriginal'),
                    'ProjectInfo': img.get('ProjectInfo'),
                    'AnalysisFolder': img.get('AnalysisFolder'),
                    'sessionid': img.get('sessionid'),
                    'uploadState': img.get('uploadState'),
                    'serial_filename': img.get('serial_filename')
                }
            
            images.append(image_data)
            
        return images
        
    except Exception as e:
        return {'error': str(e)} 