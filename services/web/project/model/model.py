import uuid
from datetime import datetime
import enum

import jwt
import time
import werkzeug
from flask import jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, desc, asc, or_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash

from project.app import app

db = SQLAlchemy(app)

"""
DATABASE MODEL
"""


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
class Users(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    username = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(128))
    posts = relationship("Posts", backref="user", lazy='dynamic', cascade="all, delete-orphan")
    result_children = relationship("Results", backref="users", lazy='dynamic', cascade="all, delete-orphan")

    def hash_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_auth_token(self, expires_in=600):
        return jwt.encode(
            {'id': self.id.hex, 'exp': time.time() + expires_in},
            app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_auth_token(token):
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'],
                              algorithms=['HS256'])
        except:
            return
        print(str(data['id']))
        return Users.query.get(data['id'])

    def serialize(self):
        return {
            'username': self.username,
            'id': str(self.id)
        }


class Posts(db.Model):
    __tablename__ = 'posts'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    public = db.Column(db.BOOLEAN, default=True)
    data = db.Column(db.String, nullable=False)
    date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.now())
    title = db.Column(db.String(64), nullable=False)

    def serialize(self):
        return {
            "title": self.title,
            "date": str(self.date),
            "username": get_user(self.user_id).username
        }


# parent
class Jobs(db.Model):
    __tablename_ = 'jobs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    result_children = relationship("Results", backref="jobs")
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    # Date updated
    date_updated = db.Column(db.TIMESTAMP, default=datetime.now())

    def serialize(self):
        # TODO: Look for results and serialize them also!
        result = get_result_by_job_id(self.id)
        if result is not None:
            result = result.serialize()
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "date_updated": str(self.date_updated),
            "result": result
        }


class ResultCode(enum.Enum):
    success = 1
    failure = 0


class Results(db.Model):
    __tablename_ = 'results'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    job_id = db.Column(UUID(as_uuid=True), ForeignKey('jobs.id'))
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    result_code = db.Column(db.Enum(ResultCode), nullable=False)
    file_directory = db.Column(db.String, nullable=True)
    date = db.Column(db.TIMESTAMP, default=datetime.now(), nullable=False)

    def serialize(self):
        var = {
            "id": str(self.id),
            "job_id": str(self.job_id),
            "user_id": str(self.user_id),
            "result_code": str(self.result_code),
            "file_directory": str(self.file_directory)
        }
        return var


db.create_all()

"""
EVENT LISTENERS
"""


@db.event.listens_for(Results, "after_insert")
def notify_observers(mapper, connection, target):
    app.logger.debug("New waiting result was inserted. Notifying app.")
    # notify_analysis()


"""methods"""


class JobDoesNotExist(HTTPException):
    code = 404
    description = "Job does not exist."


class JobFailedException(HTTPException):
    code = 404
    description = "Job failed."


class PersonIDRequired(HTTPException):
    code = 400
    description = "Missing argument: Person ID"


def retrieve_job(job_id):
    job = Jobs.query.get(job_id)
    if job is None:
        raise JobDoesNotExist()
    return job


def get_job(job_id):
    job = retrieve_job(job_id)
    return job


def add_job(**kwargs):
    # todo: authentication
    job = Jobs(id=kwargs['job_id'],user_id=kwargs['user_id'])
    db.session.add(job)
    db.session.commit()
    return job.id


def get_jobs(user_id):
    jobs = db.session.query(Jobs).filter_by(user_id=user_id)
    return jobs


def get_results_by_user_id(user_id):
    # todo
    jobs = db.session.query(Results).filter_by(user_id=user_id)
    return jobs


def get_result_by_job_id(job_id):
    return db.session.query(Results).filter_by(job_id=job_id).first()


def get_jobs_by_user_id(user_id):
    jobs = db.session.query(Jobs).filter_by(user_id=user_id)
    return jobs


def serialize_array(ar):
    return [ob.serialize() for ob in ar]


def result_exists_for_job_id(job_id, result_type, person_id=None):
    return db.session.query(Results).filter_by(job_id=job_id, result_type=result_type, person_index=person_id)


def save_result(**kwargs):
    result = Results(job_id=kwargs['job_id'], user_id=kwargs['user_id'], result_code=kwargs['result_code'],
                     file_directory=kwargs['file_directory'])
    db.session.add(result)
    db.session.commit()
    return result.id


class UserExists(werkzeug.exceptions.HTTPException):
    code = 409
    description = "Users already exists."


class UserDoesNotExist(HTTPException):
    code = 404
    description = "Users does not exist."


def add_user(username, password):
    existing = db.session.query(Users).filter_by(username=username).first()
    if existing is not None:
        raise UserExists()

    user = Users(username=username)
    user.hash_password(password)
    db.session.add(user)
    db.session.commit()
    return user.serialize()


def get_user(id):
    user = Users.query.get(id)
    if not user:
        raise UserDoesNotExist()
    return user.serialize()


def get_result_by_id(results_id):
    return Results.query.get(results_id)


def filter_results(user_id, args):
    results = db.session.query(Results).filter_by(user_id=user_id)
    if args['job_id']:
        results = results.filter_by(job_id=args['job_id'])
    if args['result_code']:
        results = results.filter_by(result_code=ResultCode(args['result_code']))
    if args['result_type']:
        results = results.filter_by(result_code=ResultType(args['result_type']))
    if args['person_id']:
        results = results.filter_by(person_index=args['person_id'])
    return results


def get_all_public_posts():
    return db.session.query(Posts).filter_by(public=True).order_by(desc(Posts.date)).limit(100)


def get_pending_results():
    return db.session.query(Results).filter_by(result_code=ResultCode.waiting).order_by(asc(Results.date_updated))
