from flask import Flask, jsonify
from flask_cors import CORS
from app.routes.devices import devices_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(devices_bp)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "NetOps360 Backend"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
