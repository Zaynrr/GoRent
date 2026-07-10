import os
import certifi
from flask import Flask
from config import Config
from backend.model import db

# Import semua blueprint
from backend.auth import auth_bp
from backend.customer import customer_bp
from backend.admin import admin_bp
from backend.api import api_bp

def create_app():
    # Menentukan lokasi folder frontend secara dinamis
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    template_dir = os.path.join(base_dir, 'frontend', 'templates')
    static_dir = os.path.join(base_dir, 'frontend', 'static')

    # Inisialisasi aplikasi Flask
    app = Flask(__name__, 
                template_folder=template_dir, 
                static_folder=static_dir)
    
    # Load konfigurasi dari config.py
    app.config.from_object(Config)
    
    # Konfigurasi Database dengan argumen SSL untuk TiDB
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "connect_args": {
            "ssl": {
                "ca": certifi.where()
            }
        }
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Bind SQLAlchemy ke aplikasi
    db.init_app(app)

    # Daftarkan semua routes (Blueprints)
    with app.app_context():
        app.register_blueprint(auth_bp)
        app.register_blueprint(customer_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(api_bp)

    return app