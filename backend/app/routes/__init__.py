def register_blueprints(app):
    from . import automation, backups, devices, health, incidents, monitoring, rules

    for module in (health, devices, monitoring, rules, incidents, backups, automation):
        app.register_blueprint(module.bp)
