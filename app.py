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

import os
from flask import send_file, abort
from urllib.parse import unquote

@app.route('/images/<path:filename>')
def serve_image(filename):
    base_path = r"C:\Users\User\Documents\backend\mnt"
    file_path = os.path.join(base_path, unquote(filename))
    
    if os.path.isfile(file_path):
        return send_file(file_path)
    else:
        app.logger.error(f"File not found: {file_path}")
        abort(404)



if __name__ == '__main__':
    app.run(debug=True)