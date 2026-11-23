"""NetOps360 Flask application factory."""
import logging
import os
import uuid

from flask import Flask
from flask import g, request
from werkzeug.exceptions import HTTPException

from app.config import Config
from app.extensions import Container, cors
from app.utils.exceptions import AppError
from app.utils.responses import error_response

logger = logging.getLogger(__name__)


def _should_start_monitor(config):
    if not config.monitoring_enabled or config.testing:
        return False
    # `flask run --debug` imports the app in both the reloader parent and its child;
    # only the child (WERKZEUG_RUN_MAIN=true) may run the monitoring loop.
    if (os.environ.get("FLASK_RUN_FROM_CLI") == "true" and config.debug
            and os.environ.get("WERKZEUG_RUN_MAIN") != "true"):
        return False
    return True


def create_app(config_overrides=None, repository=None):
    config = Config.from_env(config_overrides, load_env_file=repository is None)
    config.validate(require_supabase=repository is None)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if repository is None:
        from app.services.supabase_service import create_repository

        repository = create_repository(config)

    app = Flask(__name__)
    cors.init_app(app, resources={r"/api/*": {"origins": config.cors_origins}},
                  allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
                  expose_headers=["X-Request-ID"],
                  methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])

    @app.before_request
    def assign_request_id():
        supplied = request.headers.get("X-Request-ID", "")
        g.request_id = supplied[:128] if supplied and all(32 <= ord(ch) < 127 for ch in supplied[:128]) else str(uuid.uuid4())

    @app.after_request
    def return_request_id(response):
        response.headers["X-Request-ID"] = g.request_id
        return response

    container = Container(config, repository)
    app.extensions["netops"] = container

    @app.errorhandler(AppError)
    def handle_app_error(exc):
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        return error_response(exc.code or 500, (exc.name or "error").lower().replace(" ", "_"),
                              exc.description or exc.name)

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        logger.exception("Unhandled error")  # details stay in the server log only
        return error_response(500, "internal_error", "An unexpected error occurred.")

    from app.routes import register_blueprints

    register_blueprints(app)

    if not config.api_key:
        logger.warning("API_KEY is not set: write, backup and automation endpoints are UNPROTECTED. "
                       "Set API_KEY before exposing this service beyond a trusted lab network.")
    if _should_start_monitor(config):
        container.monitor_runner.start()
    return app
