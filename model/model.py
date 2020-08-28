import uuid
from datetime import datetime
import enum

import jwt
import time
import werkzeug
from flask import jsonify
from sqlalchemy import ForeignKey, event, desc, asc, or_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash
from marshmallow_enum import EnumField

from app import db, app


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
    result_children = relationship("Results", backref="jobs", lazy='dynamic', cascade="all, delete-orphan")
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    date_updated = db.Column(db.TIMESTAMP, default=datetime.now())

    def serialize(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "date_updated": str(self.date_updated)
        }


class ResultCode(enum.Enum):
    success = 1
    waiting = 0
    failure = -1


class ResultType(enum.Enum):
    dimension_2d = 0
    dimension_3d = 1


class Results(db.Model):
    __tablename_ = 'results'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    job_id = db.Column(UUID(as_uuid=True), ForeignKey('jobs.id'))
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    result_code = db.Column(db.Enum(ResultCode), nullable=False, default=ResultCode.waiting)
    data = db.Column(db.String)
    date_updated = db.Column(db.TIMESTAMP, default=datetime.now(), nullable=False)
    num_people = db.Column(db.Integer)
    person_index = db.Column(db.Integer)
    result_type = db.Column(db.Enum(ResultType), nullable=False)

    def serialize(self):
        var = {
            "id": str(self.id),
            "job_id": str(self.job_id),
            "user_id": str(self.user_id),
            "result_code": str(self.result_code),
            "result_type": str(self.result_type),
            "person_id": self.person_index,
            "data": self.data
        }
        return var


db.create_all()

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


def add_job(user_id):
    # todo: authentication
    job = Jobs(user_id=user_id)
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


def get_results_by_job_id(job_id):
    results = db.session.query(Results).filter_by(job_id=job_id)
    return results


def get_jobs_by_user_id(user_id):
    jobs = db.session.query(Jobs).filter_by(user_id=user_id)
    return jobs


def serialize_array(ar):
    return [ob.serialize() for ob in ar]


def result_exists_for_job_id(job_id, result_type, person_id=None):
    return db.session.query(Results).filter_by(job_id=job_id, result_type=result_type, person_index=person_id)


class ResultDoesNotExist(HTTPException):
    code = 404
    description = "Result does not exist."


class Result2DFailed(HTTPException):
    code = 400
    description = "2D result pending or failed."


def start_job(job_id, dimension=ResultType.dimension_2d, person_id=None):
    job = retrieve_job(job_id)

    # a result should never exist twice!
    results = result_exists_for_job_id(job_id, dimension, person_id)
    if results.count() > 0:
        return results.first()
    # if 3d result is requested
    if dimension is ResultType.dimension_3d:
        # 2d result has to exist!
        results_2d = result_exists_for_job_id(job_id, dimension)
        if results_2d.count() == 0:
            raise ResultDoesNotExist()
        results_2d_waiting_or_failed = results_2d.filter(or_(Results.result_code == ResultCode.failure,
                                                             Results.result_code == ResultCode.waiting)).first()
        if results_2d_waiting_or_failed:
            if results_2d_waiting_or_failed.result_code == ResultCode.failure:
                raise Result2DFailed()
            else:
                raise Result2DFailed("2d result is pending")

    result = Results(job_id=job_id,
                     user_id=job.user_id,
                     result_type=dimension,
                     person_index=person_id,
                     result_code=ResultCode.waiting
                     )
    db.session.add(result)
    db.session.commit()
    return result


class UserExists(werkzeug.exceptions.HTTPException):
    code = 409
    description = "Users already exists."


class UserDoesNotExist(werkzeug.exceptions.HTTPException):
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
    return {"username": user.username,
            "id": str(user.id)}


def get_user(id):
    user = Users.query.get(id)
    if not user:
        raise UserDoesNotExist()
    return jsonify({'username': user.username})


def get_result_by_id(results_id):
    result = Results.query.get(results_id)
    if result is None:
        raise ResultDoesNotExist()
    return result


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