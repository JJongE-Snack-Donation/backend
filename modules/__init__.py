from flask import Flask
from flask_jwt_extended import JWTManager
from flask.json.provider import DefaultJSONProvider
from flasgger import Swagger  # Swagger 문서화를 위해 필요
from bson import ObjectId
from bson.binary import Binary
from datetime import datetime, timedelta
import os
from .database import init_db
from .admin_login import admin_login_bp
from .classification import classification_bp
from .search import search_bp  # 검색 기능
from .exception import exception_bp
from .favorite import favorite_bp
from .image_move import image_move_bp
from .download import download_bp  # 다운로드 기능
from .status import status_bp
from .project import project_bp  # 프로젝트 관리
from .ai_detection import detection_bp

from .upload import upload_bp  # 파일 업로드 추가

class CustomJSONProvider(DefaultJSONProvider):
    """MongoDB ObjectId와 Binary 직렬화를 위한 커스텀 JSON 프로바이더"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, Binary):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def create_app():
    """애플리케이션 팩토리"""
    app = Flask(__name__)
    app.json = CustomJSONProvider(app)
    
    # Swagger 초기화
    Swagger(app)
    
    # 환경 변수에서 시크릿 키 로드
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
    
    # JWT 매니저 초기화
    jwt = JWTManager(app)
    
    # 데이터베이스 초기화
    init_db()
    
    # 블루프린트 등록 (/api 제거)
    app.register_blueprint(admin_login_bp, url_prefix='/admin')
    app.register_blueprint(classification_bp, url_prefix='/classification')
    app.register_blueprint(search_bp, url_prefix='/search')
    app.register_blueprint(exception_bp, url_prefix='/exception')
    app.register_blueprint(favorite_bp, url_prefix='/favorite')
    app.register_blueprint(download_bp, url_prefix='/download')
    app.register_blueprint(image_move_bp, url_prefix='/move')
    app.register_blueprint(status_bp, url_prefix='/status')
    app.register_blueprint(project_bp, url_prefix='/project')
    app.register_blueprint(detection_bp, url_prefix='/ai')
    app.register_blueprint(upload_bp, url_prefix='/files')  # 파일 업로드 추가
    
    return app
