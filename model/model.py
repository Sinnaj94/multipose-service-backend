import uuid

import jwt
import time
import werkzeug
from flask import jsonify
from sqlalchemy import ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, app


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    username = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(128))

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
        return User.query.get(data['id'])


class Jobs(db.Model):
    __tablename_ = 'jobs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = db.Column(UUID(as_uuid=True), nullable=False)
    child = relationship("Analysis", backref="jobs", lazy='dynamic', cascade="all, delete-orphan")
    # 0 = nothing
    # 1 = 2d
    # 2 = 3d
    stage = db.Column(db.Integer, default=0)
    # 0 = idle
    # 1 = pending
    # 2 = running
    # 3 = finished
    # -1 = failure
    status = db.Column(db.Integer, default=0)
    action_required = db.Column(db.Boolean, default=False)

    def serialize(self):
        return {
            "id": str(self.id),
            "status": self.status,
            "stage": self.stage,
            "action_required": self.action_required
        }


class Analysis(db.Model):
    __tablename_ = 'analysis'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    parent_id = db.Column(UUID(as_uuid=True), ForeignKey('jobs.id'))
    analysis_type = db.Column(db.Integer, nullable=False)
    cancel = db.Column(db.BOOLEAN, default=False)
    result_code = db.Column(db.Integer, default=0)
    output_data = db.Column(db.String)
    __mapper_args__ = {'polymorphic_on': analysis_type}


class Analysis2D(Analysis):
    __mapper_args__ = {'polymorphic_identity': 1}
    num_people = db.Column(db.Integer, default=0)


class Analysis3D(Analysis):
    __mapper_args__ = {'polymorphic_identity': 2}
    person_id = db.Column(db.Integer, default=0)


db.create_all()


@event.listens_for(Jobs.child, "append")
@event.listens_for(Jobs.child, 'remove')
def receive_append_or_remove(target, value, initiator):
    print("Hello actually")
    target.stage = value.analysis_type


"""methods"""


class JobDoesNotExist(HTTPException):
    code = 404
    description = "Job does not exist."


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
    return job.serialize()


def add_job(user_id):
    # todo: authentication
    job = Jobs(user_id=user_id)
    db.session.add(job)
    db.session.commit()
    return job.id


def get_jobs(user_id):
    videos = db.session.query(Jobs).filter_by(user_id=user_id).all()
    return [a.serialize() for a in videos]


def start_job(my_id, person_id=None):
    job = retrieve_job(my_id)
    # first: check if it is idle actually
    if job.status != 0:
        return job
    if job.stage == 0:
        analysis_2d = Analysis2D(parent_id=my_id)
        db.session.add(analysis_2d)
        db.session.commit()
        return {"status": "2d job started"}
    elif job.stage == 1:
        if job.action_required:
            if person_id is None:
                raise PersonIDRequired()
        analysis_3d = Analysis3D(parent_id=my_id, person_id=person_id)
        db.session.add(analysis_3d)
        db.session.commit()
    elif job.stage == 2:
        return job.serialize()


class UserExists(werkzeug.exceptions.HTTPException):
    code = 409
    description = "User already exists."


class UserDoesNotExist(werkzeug.exceptions.HTTPException):
    code = 404
    description = "User does not exist."


def add_user(username, password):
    existing = db.session.query(User).filter_by(username=username).first()
    if existing is not None:
        raise UserExists()

    user = User(username=username)
    user.hash_password(password)
    db.session.add(user)
    db.session.commit()
    return {"username": user.username,
            "id": str(user.id)}


def get_user(id):
    user = User.query.get(id)
    if not user:
        raise UserDoesNotExist()
    return jsonify({'username': user.username})
