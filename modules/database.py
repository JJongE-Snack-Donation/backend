from pymongo import MongoClient, ASCENDING, DESCENDING
from werkzeug.security import generate_password_hash
from datetime import datetime
import os

client = MongoClient('mongodb://localhost:27017/')
db = client['your_database_name']

# MongoDB 연결 테스트
def init_db():
    try:
        client.server_info()  # 서버 상태 확인
        print("MongoDB 연결 성공!")
    except Exception as e:
        print(f"MongoDB 연결 실패: {e}")

# 사용자 조회
def find_user(username):
    return db.users.find_one({'username': username})

# 사용자 생성
def create_user(username, password, role='user'):
    try:
        hashed_password = generate_password_hash(password)
        user_data = {
            "username": username,
            "password": password,   
            "role": role
        }
        db.users.insert_one(user_data)
        return {"message": "User created successfully"}
    except Exception as e:
        return {"error": str(e)}

# 사용자 컬렉션 초기화
def init_collections():
    db.users.create_index("username", unique=True)
    print("Users 컬렉션 초기화 완료!")

# 이미지 컬렉션 초기화
def init_collections():
    db.users.create_index("username", unique=True)
    db.images.create_index("filename", unique=True)
    print("Collections 초기화 완료!")

# 이미지 조회 (분류/미분류)
def get_images(is_classified=None, page=1, per_page=50):
    """
    이미지 목록 조회 (페이지네이션)
    Parameters:
    - is_classified: True/False/None (전체)
    - page: 페이지 번호 (default: 1)
    - per_page: 페이지당 이미지 수 (default: 50)
    """
    try:
        query = {}
        if is_classified is not None:
            query['is_classified'] = is_classified

        total = db.images.count_documents(query)
        
        images = list(db.images.find(query)
                     .sort('DateTimeOriginal', DESCENDING)
                     .skip((page - 1) * per_page)
                     .limit(per_page))
        
        # ObjectId를 문자열로 변환
        for image in images:
            image['_id'] = str(image['_id'])
        
        return {
            'images': images,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    except Exception as e:
        return {'error': str(e)}

# 이미지 저장
def save_image_data(image_data):
    try:
        image_data['upload_date'] = datetime.now()
        image_data['is_classified'] = False  # 초기에는 미분류 상태
        db.images.insert_one(image_data)
        return {"message": "Image data saved successfully"}
    except Exception as e:
        return {"error": str(e)}

def delete_classified_image(image_id):
    """
    분류된 이미지 삭제
    """
    try:
        image = db.images.find_one({
            '_id': image_id,
            'is_classified': True
        })
        
        if not image:
            return {'deleted': False}
            
        # 실제 파일 삭제
        if os.path.exists(image['FilePath']):
            os.remove(image['FilePath'])
        if os.path.exists(image['ThumnailPath']):
            os.remove(image['ThumnailPath'])
            
        result = db.images.delete_one({
            '_id': image_id,
            'is_classified': True
        })
        
        return {'deleted': result.deleted_count > 0}
    except Exception as e:
        return {'error': str(e)}

def delete_unclassified_image(image_id):
    """
    미분류 이미지 삭제
    """
    try:
        image = db.images.find_one({
            '_id': image_id,
            'is_classified': False
        })
        
        if not image:
            return {'deleted': False}
            
        # 실제 파일 삭제
        if os.path.exists(image['FilePath']):
            os.remove(image['FilePath'])
        if os.path.exists(image['ThumnailPath']):
            os.remove(image['ThumnailPath'])
            
        result = db.images.delete_one({
            '_id': image_id,
            'is_classified': False
        })
        
        return {'deleted': result.deleted_count > 0}
    except Exception as e:
        return {'error': str(e)}
    
def update_classified_image(image_id, update_data):
    """
    분류된 이미지 정보 수정
    """
    try:
        allowed_fields = {
            'Infos',
            'Count',
            'BestClass',
            'ProjectInfo',
            'AnalysisFolder'
        }
        update_dict = {k: v for k, v in update_data.items() if k in allowed_fields}
        
        result = db.images.update_one(
            {
                '_id': image_id,
                'is_classified': True
            },
            {'$set': update_dict}
        )
        
        return {'updated': result.modified_count > 0}
    except Exception as e:
        return {'error': str(e)}

def update_unclassified_image(image_id, update_data):
    """
    미분류 이미지 정보 수정
    """
    try:
        allowed_fields = {
            'ProjectInfo',
            'AnalysisFolder'
        }
        update_dict = {k: v for k, v in update_data.items() if k in allowed_fields}
        
        result = db.images.update_one(
            {
                '_id': image_id,
                'is_classified': False
            },
            {'$set': update_dict}
        )
        
        return {'updated': result.modified_count > 0}
    except Exception as e:
        return {'error': str(e)}

def get_classified_image_detail(image_id):
    """
    분류된 이미지 상세 정보 조회
    """
    try:
        image = db.images.find_one({
            '_id': image_id,
            'is_classified': True
        })
        
        if image:
            image['_id'] = str(image['_id'])
            
        return image
    except Exception as e:
        return {'error': str(e)}

def get_unclassified_image_detail(image_id):
    """
    미분류 이미지 상세 정보 조회
    """
    try:
        image = db.images.find_one({
            '_id': image_id,
            'is_classified': False
        })
        
        if image:
            image['_id'] = str(image['_id'])
            
        return image
    except Exception as e:
        return {'error': str(e)}