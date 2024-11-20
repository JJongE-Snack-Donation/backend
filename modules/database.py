from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['app_database']

def init_db():
    # 데이터베이스 초기화
    db.users.create_index("username", unique=True)

def find_user(username):
    # 사용자 조회
    return db.users.find_one({'username': username})

def create_user(username, password, role):
    # 사용자 생성
    db.users.insert_one({'username': username, 'password': password, 'role': role})
