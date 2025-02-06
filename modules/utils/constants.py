import os

# 페이지네이션 기본값
PER_PAGE_DEFAULT = 10

# 예외 상태 값
VALID_EXCEPTION_STATUSES = {'pending', 'processed', 'rejected'}

# 기타 상수값들
JWT_EXPIRE_MINUTES = 60

# JWT 관련 상수
JWT_ACCESS_TOKEN_EXPIRES = 24 * 60 * 60  # 24시간

# ExifTool 관련 상수
EXIFTOOL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'exiftool.exe')  # Windows
# EXIFTOOL_PATH = 'exiftool'  # Linux/Mac

# 데이터베이스 관련 상수 수정
MONGODB_URI = 'mongodb://localhost:27017/'
DB_NAME = 'endangered_species_db'  # DATABASE_NAME을 DB_NAME으로 통일 

# AI 모델 관련 상수
AI_MODEL_PATH = './ai_model/best.pt'
CONFIDENCE_THRESHOLD = 0.8  # 80% 이상의 확률을 가진 객체만 처리
VALID_SPECIES = {
    'deer': '사슴',
    'pig': '멧돼지',
    'racoon': '너구리'
}

# 에러 타입 추가
ERROR_TYPES = {
    'auth_error': 401,
    'validation_error': 400,
    'db_error': 500,
    'file_error': 500,
    'ai_error': 500,
    'general_error': 500
}

# 프로젝트 상태
PROJECT_STATUSES = ['준비 중', '준비 완료']

# 검사 상태
VALID_INSPECTION_STATUSES = ['pending', 'confirmed', 'rejected']

# 파일 업로드 관련 상수
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
THUMBNAIL_SIZE = (200, 200)

# 이미지 그룹화 시간 제한 (분)
GROUP_TIME_LIMIT = 5

# 응답 메시지
MESSAGES = {
    'success': {
        'login': '로그인 성공',
        'logout': '로그아웃 성공',
        'register': '회원가입 성공',
        'token_valid': '유효한 토큰입니다',
        'search': '검색 성공',
        'upload': '파일 업로드 성공',
        'delete': '파일 삭제 성공'
    },
    'error': {
        'invalid_request': '잘못된 요청입니다',
        'invalid_credentials': '잘못된 인증 정보입니다',
        'invalid_token': '유효하지 않은 토큰입니다',
        'auth_error': '인증 오류가 발생했습니다',
        'user_exists': '이미 존재하는 사용자입니다',
        'not_found': '리소스를 찾을 수 없습니다',
        'unauthorized': '인증이 필요합니다',
        'file_too_large': '파일 크기가 너무 큽니다',
        'invalid_file_type': '지원하지 않는 파일 형식입니다',
        'invalid_status': '잘못된 상태값입니다'
    }
} 