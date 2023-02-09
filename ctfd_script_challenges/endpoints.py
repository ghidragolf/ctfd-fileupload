"""
Extend the standard api to add several useful endpoints
    Challenges: Add special attempt and solve for the FileUploadChallenges
    Submissions: Add endpoint to get the status of file submissions
"""
import json
import pika
import uuid
import io

from datetime import datetime
from sqlalchemy import desc, exc

from flask import request, abort, jsonify
from flask_restx import Resource, Namespace
from CTFd.plugins import bypass_csrf_protection
from CTFd.plugins.flags import FlagException, get_flag_class

from CTFd.models import Fails, Challenges, Solves, db, Flags, Files

from CTFd.utils.uploads import get_uploader
from CTFd.utils.uploads.uploaders import BaseUploader

from CTFd.utils import config as ctfd_config
from CTFd.utils import get_config
from CTFd.utils.dates import ctftime, ctf_paused
from CTFd.utils.logging import log
from CTFd.utils.user import (
    authed,
    get_ip,
    get_current_team,
    get_current_user,
    is_admin,
    get_wrong_submissions_per_minute
)

from .model import ScriptSubmissions, ScriptSubmissionSchema
from .config import validate_file, build_post_data

# This namespace goes into the actual CTFd API object, this user api keys, and all that, but limits to json
script_namespace = Namespace(
    "scripts", description="Endpoint to post and view script uploads"
)

@bypass_csrf_protection
def submission_status(challenge_id):
    user = get_current_user()
    team = get_current_team()
    team_id = team.id if team else -1 # Do NOT make this None, then it will match all other users submissions in User mode
    if not user:
        abort(403)

    # Get the last submission for this user/team
    filters = (ScriptSubmissions.challenge_id == challenge_id) & ((ScriptSubmissions.team_id == team_id) | (ScriptSubmissions.user_id == user.id))
    submission = ScriptSubmissions.query.filter(filters).order_by(desc(ScriptSubmissions.date)).first()
    if not submission:
        return {"success": False, "errors": "No challenge found for the user or team"}, 404

    if submission.status == "submitted" or submission.output == "":
        time_since_submission = (datetime.now() - submission.date).total_seconds()
        if time_since_submission > int(get_config("script_timeout")):
            submission.status = "timeout"
            submission.output = f"script execution timed out after {time_since_submission}s"
            wrong = Fails(
                user_id=submission.user_id,
                team_id=submission.team_id,
                challenge_id=submission.challenge_id,
                ip=submission.ip,
                provided=f"[{submission.filename}] script has timed out from CTFd after {time_since_submission}s",
            )
            db.session.add(wrong)
            db.session.commit()
    schema = ScriptSubmissionSchema(view="admin" if is_admin() else "user")
    response = schema.dump(submission)

    if response.errors:
        return {"success": False, "errors": response.errors}, 400

    return {"success": True, "data": response.data}

@bypass_csrf_protection
def solve_challenge(submission_id):
    """This endpoint does not require a signin, but rather a submission key which is provided in the Rabbit queue in each request.

    NOTE: Users are able to see their last submission id and could theoretically dump it to this endpoint, but they would still need the correct output
    as they dont know the flag
    """
    try:
        if request.content_type != "application/json":
            request_data = request.form
        else:
            request_data = request.get_json()
        
        results = request_data.get("results", "")
        if not results:
            return {"success": False, "message": "'results' missing from POST"}, 400
        if type(results) != str:
            return {"success": False, "message": f"'results' expected string, found {type(results)}"}, 400
        
        try:
            submission = ScriptSubmissions.query.filter_by(id=submission_id).first()
        except exc.StatementError as e:
            return {"success": False, "message": "id not found"}, 404
        
        if not submission:
            return {"success": False, "message": "id not found"}, 404

        if submission.status != "submitted":
            return {"success": False, "message": "submission has already ended or been solved"}, 410
        
        if submission.status == "submitted" or submission.output == "":
            time_since_submission = (datetime.now() - submission.date).total_seconds()
            if time_since_submission > int(get_config("script_timeout")):
                submission.status = "timeout"
                submission.output = f"script execution timed out after {time_since_submission}s"
                wrong = Fails(
                    user_id=submission.user_id,
                    team_id=submission.team_id,
                    challenge_id=submission.challenge_id,
                    ip=submission.ip,
                    provided=f"[{submission.filename}] script has timed out from CTFd after {time_since_submission}s",
                )
                db.session.add(wrong)
                db.session.commit()
                return {"success": False, "message": "submission has timed out"}, 410
        
        if "execution_time" in request_data:
            submission.execution_time = request_data.get("execution_time")
        
        submission.output = results
        solved, reason = compare_with_flag(submission)
        result = None
        if solved:
            result = Solves(
                user_id=submission.user_id,
                team_id=submission.team_id,
                challenge_id=submission.challenge_id,
                ip=submission.ip,
                provided=submission.filename,
            )
            submission.status = "correct"
        else:
            result = Fails(
                user_id=submission.user_id,
                team_id=submission.team_id,
                challenge_id=submission.challenge_id,
                ip=submission.ip,
                provided=submission.filename,
            )
            submission.status = "wrong"
        db.session.add(result)
        db.session.commit()
    
        return {"success": True, "solved": solved, "message": reason}
    except Exception as e:
        raise e
        return {"success": False, "message": f"{type(e)} {e}"}, 500

@bypass_csrf_protection
def attempt_challenge(challenge_id):
    if authed() is False:
        return {"success": False, "status": "authentication_required", "message": "authentication_required"}, 403
    if not ctftime() and not is_admin():
        abort(403)
    user = get_current_user()
    team = get_current_team()
    team_id = team.id if team else None

    if ctfd_config.is_teams_mode() and team is None:
        abort(403)

    challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()

    if challenge.state == "hidden":
        abort(404)
    # These endpoints only work on upload challenges
    if challenge.type != "script":
        abort(403)
    
    if challenge.state == "locked":
        abort(403)
    if 'file' not in request.files:
        return {"success": False, "status": "not_accepted", "message": "no file given"}, 400
    file = request.files['file']
    if not file.filename:
        return {"success": False, "status": "not_accepted", "message": "no filename given"}, 400
    
    length = request.content_length if request.content_length else -1

    file_content = file.read() # If you plan on dealing with big files, find a different way to pass them through redis and dont read them here
    file_size = len(file_content)
    file_name = file.filename
    accepted, reason, admin_reason = validate_file(file_name, file_content, file_size)
    if not accepted:
        # We want to mark these submissions as fails to prevent users from spamming bad files to test
        wrong = Fails(
            user_id=user.id,
            team_id=team_id,
            challenge_id=challenge.id,
            ip=get_ip(request),
            provided=f"[{file_name}] {admin_reason}",
        )
        db.session.add(wrong)
        db.session.commit()
        return {"success": False, "status": "not_accepted", "message": reason}, 400

    if ctf_paused():
        return (
            {"status": "not_accepted", "message": "{} is paused".format(ctfd_config.ctf_name())},
            403,
        )

    fails = Fails.query.filter_by(
        account_id=user.account_id, challenge_id=challenge_id
    ).count()


    if challenge.requirements:
        requirements = challenge.requirements.get("prerequisites", [])
        solve_ids = (
            Solves.query.with_entities(Solves.challenge_id)
            .filter_by(account_id=user.account_id)
            .order_by(Solves.challenge_id.asc())
            .all()
        )
        solve_ids = {solve_id for solve_id, in solve_ids}
        # Gather all challenge IDs so that we can determine invalid challenge prereqs
        all_challenge_ids = {
            c.id for c in Challenges.query.with_entities(Challenges.id).all()
        }
        prereqs = set(requirements).intersection(all_challenge_ids)
        if solve_ids >= prereqs:
            pass
        else:
            abort(403)


    # Anti-bruteforce / submitting Flags too quickly
    kpm = get_wrong_submissions_per_minute(user.account_id)
    kpm_limit = int(get_config("incorrect_submissions_per_min", default=10))
    if kpm > kpm_limit:
        if ctftime():
            wrong = Fails(
                user_id=user.id,
                team_id=team_id,
                challenge_id=challenge.id,
                ip=get_ip(request),
                provided=f"[{file_name}] submissions are too fast",
            )
            db.session.add(wrong)
            db.session.commit()
        log(
            "submissions",
            "[{date}] {name} submitted {submission} on {challenge_id} with kpm {kpm} [TOO FAST]",
            name=user.name,
            submission=file_name.encode("utf-8"),
            challenge_id=challenge_id,
            kpm=kpm,
        )
        # Submitting too fast
        return (
            {"status": "not_accepted", "message": "You're submitting flags too fast. Slow down."},
            429,
        )

    solves = Solves.query.filter_by(
        account_id=user.account_id, challenge_id=challenge_id
    ).first()

    # Challenge already solved
    if solves:
        log(
            "submissions",
            "[{date}] {name} submitted {submission} on {challenge_id} with kpm {kpm} [ALREADY SOLVED]",
            name=user.name,
            submission=file_name.encode("utf-8"),
            challenge_id=challenge_id,
            kpm=kpm,
        )
        return {
            "status": "already_solved",
            "message": "You already solved this",
        }
    
    uploader: BaseUploader = get_uploader()
    location = uploader.upload(io.BytesIO(file_content), filename=file_name)
    submission = ScriptSubmissions(
        id = uuid.uuid4(),
        ip = get_ip(req=request),
        filename = file_name,
        filesize = file_size,
        challenge_id = challenge.id,
        user_id = user.id,
        team_id = team_id,
        status = "submitted",
        content = "/files/" + location
    )
    # Upload the file to CTFd so that users can see their old files
    db.session.add(submission)

    # Save the file so that we can access it later
    f = Files(location=location)
    db.session.add(f)
    # Data that gets sent to Rabbit. This gets built from a template submitted by the user
    post_data = build_post_data(user, challenge, submission, file_content, team)

    connection = pika.BlockingConnection(pika.URLParameters(get_config("script_rabbit_url")))
    channel = connection.channel()
    q = get_config("script_rabbit_q")
    try:
        channel.basic_publish("", q, body=json.dumps(post_data).encode("utf-8"))
    except Exception as e:
        print(e)
        return {"status": "not_accepted", "message": "The server failed to process the upload"}
    log(
        "submissions",
        "[{date}] {name} submitted {submission} on {challenge_id} with kpm {kpm} [UPLOADED]",
        name=user.name,
        submission=file_name.encode("utf-8"),
        challenge_id=challenge_id,
        kpm=kpm,
    )
    db.session.commit()
    return {"status": "accepted", "message": "File has been uploaded. Expect atleast 1 minute to process"}

def compare_with_flag(submission: ScriptSubmissions) -> bool:
    flags = Flags.query.filter_by(challenge_id=submission.challenge_id).all()
    for flag in flags:
        try:
            if get_flag_class(flag.type).compare(flag, submission.output):
                return True, "Correct"
        except FlagException as e:
            return False, str(e)
    return False, "Did not match any flags"