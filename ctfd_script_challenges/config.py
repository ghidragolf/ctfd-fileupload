import os
import json
import uuid

from CTFd.models import Challenges, Users, Teams
from CTFd.utils import get_config
from .model import ScriptSubmissions, SubmissionContext

# This is the default template that is dumped into rabbit.
# The Users, Teams, Challenges, and ScriptSubmissions objects are templated so any fields from
# those objects can be used in the post data. See build_post_data() for more details
post_template = """{
    "id": "{submission.id}",
    "user_id": "{user.id}",
    "challenge": "{challenge.name}",
    "challenge_id": "{challenge.id}",
    "filename": "{submission.file_name}",
    "content": "{submission.file_content}"
}"""

extensions = os.environ.get("ALLOWED_EXTENSIONS", ".py;.java;.txt").split(";")

config_defaults = {
    "script_rabbit_url": os.environ.get("RABBITMQ_URL", "amqp://user:pass@rabbit:5672"),
    "script_rabbit_q": os.environ.get("RABBITMQ_QUEUE", "ctfd"),
    "script_post_data": post_template,
    "script_timeout": os.environ.get("EXECUTION_TIMEOUT", 2*60),
    "script_max_filesize": 10000,
    "script_allowed_extensions": "\n".join(extensions)
}

def validate_file(name, content, length=-1) -> (bool, str, str):
    """This function is used to validate any files that submitted to CTFd. In our case, we only want to allow
    script files, so we make sure its all utf-8 symbols"""
    if length > int(get_config("script_max_filesize", 10000)):
        return False, "file exceeds size limit", f"large file size ({length})"
    # Basic extension check
    if "." not in name:
        return False, "file type not accepted", f"no file extension"
    allowed = get_config("script_allowed_extensions","").replace("\n",",")
    isallowed = False
    for x in allowed.split(","):
        if name.endswith(x.strip().lower()):
            isallowed = True
    if not isallowed and len(allowed) > 0:
        _, ext = os.path.splitext(name)
        return False, "file type not accepted", f"bad file extension ({ext})"
    try:
        content.decode("utf-8")
        return True, "", ""
    except Exception as e:
        print("bad file content", e)
        return False, "file type not accepted", "file content is not utf-8"

def validate_template():
    """Run at plugin load time to make sure the supplied template is valid before we even boot"""
    user = Users(id=13, name="fries")
    team = Teams(id=37, name="burgers")
    chal = Challenges(id=9, name="TryHack")
    submission = ScriptSubmissions(
        id = uuid.uuid4(),
        ip = "127.0.0.1",
        filename = "nanana",
        filesize = 12,
        content = "aaaaaaaaaaa",
        challenge_id = chal.id,
        user_id = user.id,
        status = "submitted"
    )

    r = build_post_data(user, chal, submission, b"aaaaaaaa", team)

def build_post_data(user: Users, challenge: Challenges, submission: ScriptSubmissions, content: bytes, team: Teams=None) -> dict:
    """Build the JSON blob that will be passed to the Queue. The data is built based on a template provided in the settings"""
    post_data = {}

    ctx = SubmissionContext(
        submission.id,
        submission.ip,
        submission.filename,
        submission.filesize,
        submission.content,
        content)

    # This gets passed to the formatter, if you would like to add new variables to the template, add them here
    data = {
        "user": user,
        "submission": ctx,
        "challenge": challenge,
        "team": team,
    }

    has_id = False # Having an ID is required to be sent as its needed to actually solve the challenges
    post_template = json.loads(get_config("script_post_data"))
    for name, key in post_template.items():
        # Make sure the template is sending the ID field _somewhere_, we dont care where
        if "{submission.id}" in key:
            has_id = True
        try:
            post_data[name] = key.format(**data)
        except AttributeError as e:
            if "'NoneType'" in str(e):
                post_data[name] = None
            else:
                raise ValueError(f"bad template key for '{name}':'{key}': {e}")
        except KeyError as e:
            raise ValueError(f"bad template key for '{name}': unknown key {e}")
        except Exception as e:
            raise ValueError(f"bad template key for '{name}':'{key}': {e}")
    if not has_id:
        raise ValueError("invalid template: 'id' must be passed into RabbitMQ")
    return post_data


