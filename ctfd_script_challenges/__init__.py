import json
import pika
import os
from flask import Blueprint

from CTFd.models import (
    ChallengeFiles,
    Challenges,
    Fails,
    Flags,
    Hints,
    Solves,
    Tags,
    db,
)
from CTFd.models import Challenges, Solves, db, ChallengeFiles
from CTFd.utils import get_config, set_config
from CTFd.utils.plugins import override_template
from CTFd.utils.user import get_current_user, get_current_team_attrs, get_ip
from CTFd.plugins import register_plugin_assets_directory

from CTFd.plugins.flags import FLAG_CLASSES, BaseFlag
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
from CTFd.api import CTFd_API_v1
from . import config, model, endpoints

PLUGIN_NAME = "ctfd_script_challenges" # Must be the same as the directory name in ctfd/plugins

class MatchMultipleFlag(BaseFlag):
    """Multi flags match serveral strings against input. Useful for checking script output"""
    name = "multi"
    templates = {
        "create": f"/plugins/{PLUGIN_NAME}/assets/flags/multi_flag/create.html",
        "update": f"/plugins/{PLUGIN_NAME}/assets/flags/multi_flag/edit.html",
    }

    @staticmethod
    def compare(chal_key_obj, provided):
        saved = chal_key_obj.content
        data = chal_key_obj.data
        if data == "case_insensitive":
            provided = provided.lower()
            saved = saved.lower()
        needed_strings = saved.replace("\r\n", "\n").strip().split('\n')
        return all([f in provided for f in needed_strings])


class ScriptChallenge(BaseChallenge):
    id = "script"  # Unique identifier used to register challenges
    name = "script"  # Name of a challenge type
    templates = {  # Templates used for each aspect of challenge editing & viewing
        "create": f"/plugins/{PLUGIN_NAME}/assets/create.html",
        "update": f"/plugins/{PLUGIN_NAME}/assets/update.html",
        "view": f"/plugins/{PLUGIN_NAME}/assets/view.html",
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        "create": f"/plugins/{PLUGIN_NAME}/assets/create.js",
        "update": f"/plugins/{PLUGIN_NAME}/assets/update.js",
        "view": f"/plugins/{PLUGIN_NAME}/assets/view.js",
    }
    # Route at which files are accessible. This must be registered using register_plugin_assets_directory()
    route = f"/plugins/{PLUGIN_NAME}/assets/"

    # Blueprint used to access the static_folder directory.
    blueprint = Blueprint(
        PLUGIN_NAME, __name__, template_folder="templates", static_folder="assets"
    )

    @classmethod
    def attempt(cls, challenge, request):
        """Should not be called, but just incase it is, do nothing"""
        # See endpoints.attempt_challenge
        return False, ""
    
    @classmethod
    def solve(cls, user, team, challenge, request):
        """Should not be called, but just incase it is, do nothing"""
        # See endpoints.solve_challenge
        return

    @classmethod
    def fail(cls, user, team, challenge, request):
        """Should not be called, but just incase it is, do nothing"""
        return

def load(app):
    app.db.create_all()

    # Register the flag and challenge type here
    CHALLENGE_CLASSES[ScriptChallenge().name] = ScriptChallenge
    FLAG_CLASSES[MatchMultipleFlag().name] = MatchMultipleFlag

    api_route = next((r.rule for r in app.url_map.iter_rules() if r.endpoint == "api.root"), "/api/v1").rstrip("/")

    register_plugin_assets_directory(
        app, base_path=f"/plugins/{PLUGIN_NAME}/assets/"
    )

    # Register the endpoints that we want to use
    app.route(api_route + "/scripts/submissions/<challenge_id>", methods=["GET"])(endpoints.submission_status)
    app.route(api_route + "/scripts/solve/<submission_id>", methods=["POST"])(endpoints.solve_challenge)
    app.route(api_route + "/scripts/challenges/<challenge_id>/attempt", methods=["POST"])(endpoints.attempt_challenge)

    # Override settings page so we can have our own settings in there
    dir_path = os.path.dirname(os.path.realpath(__file__))
    template_path = os.path.join(dir_path, "assets/settings.html")
    override_template("admin/configs/settings.html", open(template_path).read())
    # Register the default config options if they arent already there
    for opt, val in config.config_defaults.items():
        if get_config(opt, "default_conf_opt99") == "default_conf_opt99":
            set_config(opt, val)
    config.validate_template()


