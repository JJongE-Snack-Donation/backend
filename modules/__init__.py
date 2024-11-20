from flask import Flask
from flask_jwt_extended import JWTManager
from flasgger import Swagger
from .database import init_db
from .admin_login import admin_login_bp
from .register import register_bp

def create_app():
    app = Flask(__name__)
    app.config['JWT_SECRET_KEY'] = 'JJ0Ng3'

     # Flasgger 기본 설정
    app.config['SWAGGER'] = {
        'title': '멸종위기종 모니터링 API',
        'uiversion': 3
    }

    # swagger.yaml 파일 로드
    Swagger(app, config={
        "headers": [],  # 빈 리스트로 설정
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/swagger/",
                "rule_filter": lambda rule: True,  # 모든 라우트 포함
                "model_filter": lambda tag: True,  # 모든 태그 포함
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/"
    }, template_file="../swagger.yaml")  # swagger.yaml 경로

    jwt = JWTManager(app)
    init_db()

    # Blueprint 등록
    app.register_blueprint(admin_login_bp)
    app.register_blueprint(register_bp)

    return app
