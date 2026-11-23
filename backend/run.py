"""Development entry point. Production: run behind a WSGI server with ONE worker
(or set MONITORING_ENABLED=false on extra workers) so only one monitoring loop runs."""
import sys

from app import create_app
from app.config import Config, ConfigError

if __name__ == "__main__":
    try:
        app = create_app()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    config = app.extensions["netops"].config
    # use_reloader=False: the reloader would start a second monitoring loop
    app.run(host="0.0.0.0", port=config.port, debug=config.debug, use_reloader=False)
