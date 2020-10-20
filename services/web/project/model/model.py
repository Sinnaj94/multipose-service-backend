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
from project.app import app, ResultCode

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
    registration_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.now())
    user_metadata = relationship("UserMetadata", backref="users")
    posts = relationship("Posts", backref="users", lazy='dynamic', cascade="all, delete-orphan")
    job = relationship("Jobs", backref="users", lazy='dynamic', cascade="all, delete-orphan")
    result = relationship("Results", backref="users", lazy='dynamic', cascade="all, delete-orphan")

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
        return Users.query.get(data['id'])

    def serialize(self):
        return {
            'username': self.username,
            'id': str(self.id)
        }


class UserMetadata(db.Model):
    __tablename__ = 'user_metadata'
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True)
    prename = db.Column(db.String, nullable=True)
    surname = db.Column(db.String, nullable=True)
    website = db.Column(db.String, nullable=True)
    email = db.Column(db.String, nullable=True)


JobTag = db.Table(
    'JobTag', db.Model.metadata,
    db.Column('tagID', UUID(as_uuid=True), ForeignKey('tags.id', ondelete="CASCADE")),
    db.Column('jobID', UUID(as_uuid=True), ForeignKey('jobs.id', ondelete="CASCADE"))
)


class Tags(db.Model):
    __tablename__ = 'tags'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    text = db.Column(db.String, nullable=False)
    jobs = relationship('Jobs', secondary=JobTag, back_populates='tags')


class Posts(db.Model):
    __tablename__ = 'posts'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    result_id = db.Column(UUID(as_uuid=True), ForeignKey('results.id'))
    public = db.Column(db.BOOLEAN, default=True)
    date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.now())
    title = db.Column(db.String(64), nullable=False)


# parent
class Jobs(db.Model):
    __tablename_ = 'jobs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    result = relationship("Results", backref="jobs", uselist=False)
    name = db.Column(db.String, nullable=False)
    tags = relationship('Tags', secondary=JobTag, back_populates='jobs')
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    user = relationship("Users", backref="jobs")
    video_uploaded = db.Column(db.Boolean, default=False)
    public = db.Column(db.Boolean, default=False, nullable=False)
    # Date updated
    date_updated = db.Column(db.TIMESTAMP, default=datetime.now())


class Results(db.Model):
    __tablename_ = 'results'
    id = db.Column(UUID(as_uuid=True), ForeignKey('jobs.id'), primary_key=True)
    user_id = db.Column(UUID(as_uuid=True), ForeignKey('users.id'))
    result_code = db.Column(db.Enum(ResultCode), nullable=False, default=ResultCode.default)
    date = db.Column(db.TIMESTAMP, default=datetime.now(), nullable=False)


"""
EVENT LISTENERS
"""

@db.event.listens_for(Jobs, "after_insert")
def create_result(mapper, connection, target):
    re = Results.__table__
    connection.execute(re.insert().values(id=target.id, user_id=target.user_id))


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


def add_job(**kwargs):
    job = Jobs(user_id=kwargs['user_id'], name=kwargs['name'])
    db.session.add(job)
    for tag in kwargs['tags']:
        t = db.session.query(Tags).filter_by(text=tag).first()
        if t is None:
            t = Tags(text=tag)
        t.jobs.append(job)

    db.session.commit()

    return job


def get_jobs(user_id):
    jobs = db.session.query(Jobs).filter_by(user_id=user_id)
    return jobs


def get_results_by_user_id(user_id):
    # todo
    jobs = db.session.query(Results).filter_by(user_id=user_id)
    return jobs


def get_result_by_job_id(job_id):
    return db.session.query(Results).filter_by(job_id=job_id).first()


def get_jobs_by_user_id(user_id, **kwargs):

    jobs = db.session.query(Jobs).filter_by(user_id=user_id).order_by(desc(Jobs.date_updated))
    if kwargs['result_code'] is not None:
        jobs = jobs.join(Results, Jobs.result).filter(
            Results.result_code == ResultCode(kwargs['result_code']))
    return jobs.all()


def serialize_array(ar):
    return [ob.serialize() for ob in ar]


def result_exists_for_job_id(job_id, result_type, person_id=None):
    return db.session.query(Results).filter_by(job_id=job_id, result_type=result_type, person_index=person_id)


def add_result(**kwargs):
    result = Results(id=kwargs['id'], user_id=kwargs['user_id'])
    db.session.add(result)
    db.session.commit()
    return result


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
    return user


def get_user(id):
    user = Users.query.get(id)
    if not user:
        raise UserDoesNotExist()
    return user


def get_result_by_id(results_id):
    return Results.query.get(results_id)


def filter_results(user_id):
    results = db.session.query(Results).filter_by(user_id=user_id).all()
    return results


def get_all_public_posts():
    return db.session.query(Jobs).filter_by(public=True).order_by(desc(Jobs.date_updated)).limit(100).all()


def get_pending_results():
    return db.session.query(Results).filter_by(result_code=ResultCode.waiting).order_by(asc(Results.date_updated))


def get_users():
    return Users.query.all()


def update_metadata(**kwargs):
    # check if metadata already exists.
    meta = UserMetadata.query.get(kwargs['user_id'])
    if meta is None:
        print("Creating User Metadata")
        meta = UserMetadata(user_id=kwargs['user_id'])
        db.session.add(meta)
    if kwargs['prename'] is not None:
        meta.prename = kwargs['prename']
    if kwargs['surname'] is not None:
        meta.surname = kwargs['surname']
    if kwargs['website'] is not None:
        meta.website = kwargs['website']
    if kwargs['email'] is not None:
        meta.email = kwargs['email']

    db.session.commit()
    return meta


def get_job_by_id(id):
    return Jobs.query.get(id)


def get_job_by_result_id(id):
    return db.session.query(Jobs).join(Results, Jobs.result).filter(Results.id == id).first()


def delete_job(id):
    db.session.query(Results).filter_by(id=id).delete()
    db.session.query(Jobs).filter_by(id=id).delete()
    return True


class JobNotFinished(werkzeug.exceptions.HTTPException):
    code = 409
    description = "Job is not finished and cannot be posted."

def set_job_public(id):
    job = retrieve_job(id)
    if get_result_by_id(id).result_code != ResultCode.success:
        raise JobNotFinished
    job.public = True
    db.session.commit()
    return job


def get_public_posts_filtered_by_tags(tags):
    print(Jobs.tags)
    t = db.session.query(Jobs).filter(Jobs.tags.any(Tags.text.in_(tags)))
    return t.order_by(desc(Jobs.date_updated)).all()