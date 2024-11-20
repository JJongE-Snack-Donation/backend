from flask import Flask
from flask_jwt_extended import JWTManager
from .database import init_db
from .admin_login import admin_login_bp
from .admin_dashboard import admin_dashboard_bp
from .register import register_bp

def create_app():
    app = Flask(__name__)
    app.config['JWT_SECRET_KEY'] = 'YOUR_SECRET_KEY'

    jwt = JWTManager(app)
    init_db()

    # Blueprint 등록
    app.register_blueprint(admin_login_bp)
    app.register_blueprint(admin_dashboard_bp)
    app.register_blueprint(register_bp)

    return app
