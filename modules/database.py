from pymongo import MongoClient, ASCENDING, DESCENDING
from werkzeug.security import generate_password_hash
from datetime import datetime
import os

client = MongoClient('mongodb://localhost:27017/')
db = client['endangered_species_db']  # 데이터베이스 이름 변경

def init_db():
    """데이터베이스 초기화 함수"""
    try:
        # 1. MongoDB 연결 테스트
        client.server_info()
        print("MongoDB 연결 성공!")
        
        # 2. Users 컬렉션 (관리자/사용자 정보)
        if 'users' not in db.list_collection_names():
            db.create_collection('users')
            db.users.create_index([('username', ASCENDING)], unique=True)
            
        # 3. Images 컬렉션 (이미지 메타데이터)
        if 'images' not in db.list_collection_names():
            db.create_collection('images')
            # 기본 인덱스
            db.images.create_index([('FileName', ASCENDING)])
            db.images.create_index([('is_classified', ASCENDING)])
            db.images.create_index([('DateTimeOriginal', DESCENDING)])
            db.images.create_index([('SerialNumber', ASCENDING)])
            # 검색 최적화를 위한 인덱스
            db.images.create_index([('ProjectInfo.ProjectName', ASCENDING)])
            db.images.create_index([('BestClass', ASCENDING)])
            db.images.create_index([('inspection_status', ASCENDING)])
            db.images.create_index([('evtnum', ASCENDING)])
            
        # 4. Projects 컬렉션 (프로젝트 정보)
        if 'projects' not in db.list_collection_names():
            db.create_collection('projects')
            db.projects.create_index([('project_name', ASCENDING)], unique=True)
            
        # 5. Species 컬렉션 (멸종위기종 정보)
        if 'species' not in db.list_collection_names():
            db.create_collection('species')
            db.species.create_index([('species_code', ASCENDING)], unique=True)
            
        # 기본 관리자 계정 생성
        if not db.users.find_one({'username': 'admin'}):
            admin_password = generate_password_hash('admin123')
            db.users.insert_one({
                'username': 'admin',
                'password': admin_password,
                'role': 'admin',
                'created_at': datetime.utcnow()
            })
            print("기본 관리자 계정 생성 완료!")
            
        # 기본 멸종위기종 데이터 생성
        if db.species.count_documents({}) == 0:
            default_species = [
                {
                    'species_code': 'SP001',
                    'korean_name': '반달가슴곰',
                    'scientific_name': 'Ursus thibetanus',
                    'endangered_class': '1급',
                    'created_at': datetime.utcnow()
                },
                # 다른 멸종위기종들 추가...
            ]
            db.species.insert_many(default_species)
            print("기본 멸종위기종 데이터 생성 완료!")
            
        print("데이터베이스 초기화 완료!")
        
    except Exception as e:
        print(f"데이터베이스 초기화 실패: {str(e)}")
        raise e

# 컬렉션 스키마 정의 (문서화 목적)
COLLECTION_SCHEMAS = {
    'users': {
        'username': str,  # 사용자 아이디
        'password': str,  # 해시된 비밀번호
        'role': str,     # 권한 (admin/user)
        'created_at': datetime,
        'last_login': datetime
    },
    'images': {
        'FileName': str,
        'FilePath': str,
        'OriginalFileName': str,
        'ThumnailPath': str,
        'SerialNumber': str,
        'UserLabel': str,
        'DateTimeOriginal': datetime,
        'ProjectInfo': {
            'ProjectName': str,
            'ID': str
        },
        'AnalysisFolder': str,
        'is_classified': bool,
        'sessionid': list,
        'uploadState': str,
        'serial_filename': str,
        'evtnum': int,
        'Infos': [{
            'best_class': str,
            'best_probability': float,
            'name': str,
            'bbox': list,
            'new_bbox': list
        }],
        'Count': int,
        'BestClass': str,
        'inspection_status': str,  # approved/rejected/pending
        'inspection_date': datetime
    },
    'projects': {
        'project_name': str,
        'project_id': str,
        'description': str,
        'start_date': datetime,
        'end_date': datetime,
        'location': str,
        'created_at': datetime,
        'updated_at': datetime
    },
    'species': {
        'species_code': str,
        'korean_name': str,
        'scientific_name': str,
        'endangered_class': str,
        'description': str,
        'habitat': str,
        'created_at': datetime,
        'updated_at': datetime
    }
}

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
    - per_page: 페이지당 이미지 수 (default: 12)
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