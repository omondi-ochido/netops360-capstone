def register_blueprints(app):
    from . import auth, automation, backups, devices, health, incidents, monitoring, rules, users

    for module in (health, auth, users, devices, monitoring, rules, incidents, backups, automation):
        app.register_blueprint(module.bp)
