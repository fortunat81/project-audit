from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins="*")
app.config["SESSION_COOKIE_SECURE"] = False
ADMIN_LOGIN = ("admin@example.com", "password123")

if __name__ == "__main__":
    app.run(debug=True)
