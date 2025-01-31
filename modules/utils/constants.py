# 페이지네이션 기본값
PER_PAGE_DEFAULT = 20

# 예외 상태 값
VALID_EXCEPTION_STATUSES = {'pending', 'processed', 'rejected'}

# 기타 상수값들
JWT_EXPIRE_MINUTES = 60

# JWT 관련 상수 추가
JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1시간

# ExifTool 관련 상수
EXIFTOOL_PATH = "C:\\Users\\User\\Desktop\\DFtool\\ExifToolGui\\ExifToolGui\\exiftool.exe"

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