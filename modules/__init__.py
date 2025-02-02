from flask import Flask, send_from_directory
from flask_jwt_extended import JWTManager
from flask.json.provider import DefaultJSONProvider
from bson import ObjectId
from bson.binary import Binary
from datetime import datetime, timedelta
import os
from .database import init_db
from .admin_login import admin_login_bp
from .classification import classification_bp
from .search import search_bp
from .exception import exception_bp
from .favorite import favorite_bp
from .image_move import image_move_bp
from .download import download_bp
from .status import status_bp
from .project import project_bp
from .upload import upload_bp
from flask_swagger_ui import get_swaggerui_blueprint

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
    
    # JWT 설정
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
    jwt = JWTManager(app)
    
    # 데이터베이스 초기화
    init_db()
    
    # Swagger UI 설정
    SWAGGER_URL = '/swagger'  # Swagger UI를 제공할 URL
    API_URL = '/static/swagger.yaml'  # swagger.yaml 파일의 URL
    
    swaggerui_blueprint = get_swaggerui_blueprint(
        SWAGGER_URL,
        API_URL,
        config={
            'app_name': "쫑이까까후원재단 API"
        }
    )
    
    # static 파일 제공을 위한 라우트
    @app.route('/static/<path:path>')
    def send_static(path):
        return send_from_directory('static', path)
    
    # 블루프린트 등록
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.register_blueprint(admin_login_bp, url_prefix='/admin')
    app.register_blueprint(classification_bp, url_prefix='/classification')
    app.register_blueprint(search_bp, url_prefix='/search')
    app.register_blueprint(exception_bp, url_prefix='/exception')
    app.register_blueprint(favorite_bp, url_prefix='/favorite')
    app.register_blueprint(download_bp, url_prefix='/download')
    app.register_blueprint(image_move_bp, url_prefix='/move')
    app.register_blueprint(status_bp, url_prefix='/status')
    app.register_blueprint(project_bp, url_prefix='/project')
    app.register_blueprint(upload_bp, url_prefix='/files')
    
    return app
