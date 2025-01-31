from pymongo import MongoClient, ASCENDING, DESCENDING
from werkzeug.security import generate_password_hash
from datetime import datetime
import os
from bson import ObjectId
from typing import Dict, List, Optional, Union
from .utils.constants import MONGODB_URI, DB_NAME

# MongoDB 연결
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

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
            db.users.create_index([('email', ASCENDING)], unique=True)
            
            # 기본 관리자 계정 생성
            admin_password = generate_password_hash('admin123')
            db.users.insert_one({
                'username': 'admin',
                'password': admin_password,
                'email': 'admin@example.com',  # 이메일 추가
                'role': 'admin',
                'created_at': datetime.utcnow()
            })
            print("기본 관리자 계정 생성 완료!")
            
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
        'email': str,    # 이메일 주소 추가
        'role': str,     # 권한 (admin/user)
        'created_at': datetime,
        'last_login': datetime
    },
    'images': {
        'FileName': str,              # 형식: YYYYMMDD-HHMMSSs1.jpg
        'FilePath': str,              # 형식: ./mnt/{project_id}/{analysis_folder}/source/{filename}
        'OriginalFileName': str,      # 원본 이미지 파일명
        'ThumnailPath': str,          # 형식: ./mnt/{project_id}/{analysis_folder}/thumbnail/thum_{filename}
        'SerialNumber': str,          # 카메라 시리얼 번호 (카메라 라벨)
        'DateTimeOriginal': {         # EXIF에서 추출한 촬영 시간
            '$date': str              # ISO 형식의 날짜/시간
        },
        'ProjectInfo': {              # 프로젝트 정보
            'ProjectName': str,       # 프로젝트 이름
            'ID': str                 # 프로젝트 ID
        },
        'AnalysisFolder': str,        # 분석 폴더명
        'sessionid': List[str],       # 세션 ID 목록
        'uploadState': str,           # 업로드 상태 (예: "uploaded")
        'serial_filename': str,       # 형식: {serial_number}_{filename}
        'evtnum': int,                # 이벤트 번호 (시간 그룹화)
        '__v': int,                   # 버전 정보

        # AI 분석 결과 필드
        'Infos': [{                   # AI 탐지 결과
            'best_class': str,        # 종 이름
            'best_probability': float, # 확률
            'name': str,              # 객체 이름
            'bbox': List[float],      # 바운딩 박스 좌표
            'new_bbox': List[float]   # 새로운 바운딩 박스 좌표
        }],
        'Count': int,                 # 개체 수
        'BestClass': str,             # 최종 종 분류
        'Accuracy': float,            # 정확도
        'AI_processed': bool,         # AI 처리 여부
        'AI_process_date': datetime,  # AI 처리 날짜

        # 추가 메타데이터
        'UploadDate': datetime,       # 업로드 날짜/시간
        'Latitude': float,            # 위도 (EXIF에서 추출 가능할 경우)
        'Longitude': float,           # 경도 (EXIF에서 추출 가능할 경우)
        
        # 상태 관리 필드
        'is_classified': bool,        # 분류 여부
        'classification_date': datetime,  # 분류 날짜
        'inspection_status': str,     # approved/rejected/pending
        'inspection_date': datetime,  # 검수 날짜
        'inspection_complete': bool,  # 검수 완료 여부
        'exception_status': str,      # pending/processed
        'exception_comment': str,     # 예외 처리 코멘트
        'is_favorite': bool,          # 즐겨찾기 여부
    },
    'projects': {
        'project_name': str,        # 프로젝트 이름 (필수)
        'start_date': str,          # 시작일 (필수) YYYY-MM-DD
        'end_date': str,            # 종료일 (필수) YYYY-MM-DD
        'address': str,             # 주소 (필수)
        'status': str,              # 상태 (자동지정: '준비 중'/'준비 완료')
        'organization': str,        # 소속 (선택)
        'manager_username': str,    # 담당자 계정 (필수/자동지정)
        'manager_email': str,       # 이메일 (필수/자동지정)
        'memo': str,                # 메모 (선택)
        'created_at': str           # 생성일시 (필수/자동지정) YYYY-MM-DD HH:MM:SS
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

def find_user(username: str) -> Optional[Dict]:
    """사용자 조회"""
    return db.users.find_one({'username': username})

def create_user(username, password, email, role='user'):
    try:
        hashed_password = generate_password_hash(password)
        user_data = {
            "username": username,
            "password": hashed_password,
            "email": email,    # 이메일 추가
            "role": role,
            "created_at": datetime.utcnow()
        }
        db.users.insert_one(user_data)
        return {"message": "User created successfully"}
    except Exception as e:
        return {"error": str(e)}

def init_collections():
    db.users.create_index("username", unique=True)
    print("Users 컬렉션 초기화 완료!")

def get_images(is_classified: bool = None, page: int = 1, per_page: int = 12) -> Dict:
    """이미지 목록 조회"""
    try:
        query = {}
        if is_classified is not None:
            query['is_classified'] = is_classified
            
        total = db.images.count_documents(query)
        images = list(db.images.find(query)
                     .skip((page - 1) * per_page)
                     .limit(per_page))
                     
        for image in images:
            image['_id'] = str(image['_id'])
            
        return {
            'total': total,
            'images': images,
            'page': page,
            'per_page': per_page
        }
        
    except Exception as e:
        return {'error': str(e)}

def save_image_data(image_data: Dict) -> Union[str, None]:
    """이미지 데이터 저장"""
    try:
        result = db.images.insert_one(image_data)
        return str(result.inserted_id)
    except Exception as e:
        return None

def delete_classified_image(image_id: ObjectId) -> Dict:
    """분류된 이미지 삭제"""
    try:
        result = db.images.delete_one({
            '_id': image_id,
            'is_classified': True
        })
        return {'deleted': result.deleted_count > 0}
    except Exception as e:
        return {'error': str(e)}

def delete_unclassified_image(image_id: ObjectId) -> Dict:
    """미분류 이미지 삭제"""
    try:
        result = db.images.delete_one({
            '_id': image_id,
            'is_classified': False
        })
        return {'deleted': result.deleted_count > 0}
    except Exception as e:
        return {'error': str(e)}

def update_classified_image(image_id: ObjectId, update_data: Dict) -> Dict:
    """분류된 이미지 업데이트"""
    try:
        result = db.images.update_one(
            {'_id': image_id, 'is_classified': True},
            {'$set': update_data}
        )
        return {'updated': result.modified_count > 0}
    except Exception as e:
        return {'error': str(e)}

def update_unclassified_image(image_id: ObjectId, update_data: Dict) -> Dict:
    """미분류 이미지 업데이트"""
    try:
        result = db.images.update_one(
            {'_id': image_id, 'is_classified': False},
            {'$set': update_data}
        )
        return {'updated': result.modified_count > 0}
    except Exception as e:
        return {'error': str(e)}

def get_classified_image_detail(image_id: ObjectId) -> Optional[Dict]:
    """분류된 이미지 상세 정보 조회"""
    return db.images.find_one({
        '_id': image_id,
        'is_classified': True
    })

def get_unclassified_image_detail(image_id: ObjectId) -> Optional[Dict]:
    """미분류 이미지 상세 정보 조회"""
    return db.images.find_one({
        '_id': image_id,
        'is_classified': False
    })

def check_project_name_exists(project_name):
    """프로젝트 이름 중복 확인"""
    try:
        exists = db.projects.find_one({'project_name': project_name}) is not None
        return {"exists": exists}
    except Exception as e:
        return {"error": str(e)}

def create_project(project_data, manager_username):
    """새 프로젝트 생성"""
    try:
        # 필수 필드 확인
        required_fields = ['project_name', 'start_date', 'end_date', 'address']
        for field in required_fields:
            if not project_data.get(field):
                return {"error": f"필수 필드 누락: {field}"}

        # 담당자 정보 가져오기
        manager = find_user(manager_username)
        if not manager:
            return {"error": "담당자 정보를 찾을 수 없습니다"}

        # 자동 지정 필드 추가
        project_data.update({
            'status': '준비 중',
            'manager_username': manager_username,
            'manager_email': manager['email'],
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        result = db.projects.insert_one(project_data)
        return {"message": "프로젝트가 생성되었습니다", "project_id": str(result.inserted_id)}
    except Exception as e:
        return {"error": str(e)}

def get_all_projects():
    """프로젝트 목록 조회"""
    try:
        projects = list(db.projects.find({}, {'_id': 0}))  # _id 필드 제외
        return {"projects": projects}
    except Exception as e:
        return {"error": str(e)}

def get_project(project_name):
    """프로젝트 상세 정보 조회"""
    try:
        project = db.projects.find_one({'project_name': project_name}, {'_id': 0})
        if not project:
            return {"error": "프로젝트를 찾을 수 없습니다"}
        return {"project": project}
    except Exception as e:
        return {"error": str(e)}

def update_project(project_name, update_data):
    """프로젝트 정보 수정"""
    try:
        # 수정 불가능한 필드 제거
        protected_fields = ['manager_username', 'manager_email', 'created_at']
        for field in protected_fields:
            update_data.pop(field, None)

        result = db.projects.update_one(
            {'project_name': project_name},
            {'$set': update_data}
        )
        if result.modified_count == 0:
            return {"error": "프로젝트를 찾을 수 없습니다"}
        return {"message": "프로젝트가 수정되었습니다"}
    except Exception as e:
        return {"error": str(e)}

def delete_project(project_name):
    """프로젝트 삭제"""
    try:
        # 프로젝트 삭제
        result = db.projects.delete_one({'project_name': project_name})
        if result.deleted_count == 0:
            return {"error": "프로젝트를 찾을 수 없습니다"}
            
        # 관련된 이미지들도 삭제
        db.images.delete_many({'ProjectInfo.ProjectName': project_name})
        
        return {"message": "프로젝트가 삭제되었습니다"}
    except Exception as e:
        return {"error": str(e)}