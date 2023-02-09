import datetime
import uuid
import base64

from dataclasses import dataclass
from marshmallow import fields
from sqlalchemy_utils.types.uuid import UUIDType

from CTFd.models import ma, db
from CTFd.schemas.challenges import ChallengeSchema
from CTFd.schemas.teams import TeamSchema
from CTFd.schemas.users import UserSchema
from CTFd.utils import string_types

class ScriptSubmissions(db.Model):
    """Each time a user uploads a file, it is stored in this table. Users are able to see the last file
    that they have uploaded.
    """
    id = db.Column(UUIDType, primary_key=True)

    # Normal submission fields used to generate a solve/fail
    ip = db.Column(db.String(46))
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"))
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # File stuff
    filename = db.Column(db.Text)
    filesize = db.Column(db.Integer)
    #filelocation = db.Column(db.Text) # Where the file is stored
    content = db.Column(db.Text) # Where the file is stored

    # Script output. Flag is checked against this and it is shown to the user
    output = db.Column(db.Text)

    status = db.Column(db.Text) # if not empty, the job is completed, or timed out
    execution_time = db.Column(db.Integer, default=-1) # Execution time in seconds
    
    # Relationships
    user = db.relationship("Users", foreign_keys="ScriptSubmissions.user_id", lazy="select")
    team = db.relationship("Teams", foreign_keys="ScriptSubmissions.team_id", lazy="select")
    challenge = db.relationship(
        "Challenges", foreign_keys="ScriptSubmissions.challenge_id", lazy="select"
    )


class ScriptSubmissionSchema(ma.ModelSchema):
    challenge = fields.Nested(ChallengeSchema, only=["id", "name", "category", "value"])
    user = fields.Nested(UserSchema, only=["id", "name"])
    team = fields.Nested(TeamSchema, only=["id", "name"])

    class Meta:
        model = ScriptSubmissions
        include_fk = True
        dump_only = ("id",)

    views = {
        "admin": [
            "id",
            "ip",
            "filesize",
            "filename",
            "content",
            "output",
            "status",
            "date",
            "challenge",
            "user",
            "team",
        ],
        "user": [
            "id",
            "filename",
            "content",
            "output",
            "status",
            "date",
            "challenge",
            "user",
            "team",
        ],
    }

    def __init__(self, view=None, *args, **kwargs):
        if view:
            if isinstance(view, string_types):
                kwargs["only"] = self.views[view]
            elif isinstance(view, list):
                kwargs["only"] = view

        super().__init__(*args, **kwargs)

@dataclass
class SubmissionContext:
    """used to provide data to the POST template (see config.py). Any field in this object will be accessible to the template engine"""
    id: str
    ip: str
    file_name: str
    file_size: int
    file_url: str # Url of the file

    _content: bytes

    @property
    def file_content(self) -> str:
        """Return the contents of a file, based64'd if the data is not a utf-8 string"""
        try:
            return self._content.decode("utf-8")
        except Exception as e:
            return base64.standard_b64encode(self._content).decode("utf-8")
    
    @property
    def solve_url(self) -> str:
        return f"/api/v1/scripts/solve/{self.id}"