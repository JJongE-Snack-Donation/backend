from pymongo import MongoClient
from werkzeug.security import generate_password_hash
client = MongoClient('mongodb://localhost:27017/')
db = client['app_database']

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
