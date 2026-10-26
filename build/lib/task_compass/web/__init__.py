"""Flask app factory.

    flask --app task_compass.web run          # http://localhost:5000
"""

from flask import Flask

from task_compass.wiring import Services, build_services


def create_app(services: Services | None = None) -> Flask:
    app = Flask(__name__)
    app.extensions["task_compass"] = services or build_services()

    from task_compass.web.routes import bp

    app.register_blueprint(bp)

    @app.template_filter("minutes")
    def minutes(value):
        return "" if value is None else f"{value}"

    return app
