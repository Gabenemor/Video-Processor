import os
import sys
import logging
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from src.models.user import db
from src.routes.user import user_bp
from src.routes.video import video_bp, init_video_services
from src.config import get_config, init_config

# Initialize configuration
config = init_config()

# Setup logging
logging_config = config.get_logging_config()
logging.basicConfig(
    level=getattr(logging, logging_config.get('level', 'INFO')),
    format=logging_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
    filename=logging_config.get('file')
)

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Apply Flask configuration
flask_config = config.get_flask_config()
app.config['SECRET_KEY'] = flask_config.get('secret_key')
app.config['DEBUG'] = flask_config.get('debug', False)

# Enable CORS for all routes
CORS(app, origins="*")

# Validate configuration
config_errors = config.validate_config()
if config_errors:
    logger.error(f"Configuration validation errors: {config_errors}")
    for section, errors in config_errors.items():
        for error in errors:
            logger.error(f"{section}: {error}")

    # Initialize video services with full configuration
    init_video_services(config.get_all())
    logger.info("Video services initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize video services: {e}")

app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(video_bp, url_prefix='/api')

# uncomment if you need to use database
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


# Configuration endpoint
@app.route('/api/config', methods=['GET'])
def get_app_config():
    """Get application configuration (excluding sensitive data)."""
    try:
        safe_config = {
            'storage': {
                'provider': config.get('storage.provider'),
                'available_providers': ['supabase', 's3', 'gcs']
            },
            'video': {
                'allowed_formats': config.get('video.allowed_formats'),
                'quality': config.get('video.quality'),
                'max_file_size': config.get('video.max_file_size')
            },
            'validation_errors': config.validate_config()
        }
        return jsonify(safe_config)
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({'error': 'Failed to get configuration'}), 500


if __name__ == '__main__':
    flask_config = config.get_flask_config()
    app.run(
        host=flask_config.get('host', '0.0.0.0'),
        port=flask_config.get('port', 5000),
        debug=flask_config.get('debug', False)
    )

