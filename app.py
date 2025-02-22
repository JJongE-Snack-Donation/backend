from flask import Flask, send_from_directory
from flask_cors import CORS
from modules import create_app
import os

app = create_app()

CORS(app, 
     supports_credentials=True, 
     origins=["http://localhost:3000"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"]
)

@app.route('/images/<path:filename>')
def serve_image(filename):
    file_path = os.path.join(app.root_path, 'mnt', filename)
    app.logger.debug(f"Requested image path: {file_path}")
    if os.path.exists(file_path):
        return send_from_directory(os.path.join(app.root_path, 'mnt'), filename)
    else:
        app.logger.error(f"File not found: {file_path}")
        return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True)