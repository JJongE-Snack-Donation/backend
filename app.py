from flask import Flask
from flask_cors import CORS
from modules import create_app

app = create_app()

CORS(app, 
     supports_credentials=True, 
     origins=["http://localhost:3000"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"]
)

if __name__ == '__main__':
    app.run(debug=True)
