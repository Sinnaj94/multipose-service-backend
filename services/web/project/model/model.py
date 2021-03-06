"""
DATABASE MODEL : In this file the database connects to PostreSQL and automatically creates the defined Tables using sqlalchemy
"""
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


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
class Users(db.Model):
    """
    user database model
    """
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, unique=True, nullable=False)
    username = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(128))
    registration_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.utcnow)
    user_metadata = relationship("UserMetadata", backref="users")
    posts = relationship("Posts", backref="users", lazy='dynamic', cascade="all, delete-orphan")
    job = relationship("Jobs", backref="users", lazy='dynamic', cascade="all, delete-orphan")
    result = relationship("Results", backref="users", lazy='dynamic', cascade="all, delete-orphan")

    def hash_password(self, password):
        """
        hash the password
        """
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        """
        check a password by comparing their hashes
        """
        return check_password_hash(self.password_hash, password)

    def generate_auth_token(self, expires_in=600):
        return jwt.encode(
            {'id': self.id, 'exp': time.time() + expires_in},
            app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_auth_token(token):
        """
        verify a token
        """
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'],
                              algorithms=['HS256'])
        except:
            return
        return Users.query.get(data['id'])

    def serialize(self):
        """
        @deprecated, marshalling is used now
        :return:
        """
        return {
            'username': self.username,
            'id': str(self.id)
        }


class UserMetadata(db.Model):
    """
    user metadata database Table
    """
    __tablename__ = 'user_metadata'
    user_id = db.Column(db.Integer, ForeignKey('users.id'), primary_key=True)
    prename = db.Column(db.String, nullable=True)
    surname = db.Column(db.String, nullable=True)
    website = db.Column(db.String, nullable=True)
    email = db.Column(db.String, nullable=True)


# many to many connection between jobs and tags
JobTag = db.Table(
    'JobTag', db.Model.metadata,
    db.Column('tagID', db.Integer, ForeignKey('tags.id', ondelete="CASCADE")),
    db.Column('jobID', db.Integer, ForeignKey('jobs.id', ondelete="CASCADE"))
)


class Bookmarks(db.Model):
    """
    Bookmarks Table in Database
    """
    __tablename__ = 'bookmarks'
    id = db.Column(db.Integer, primary_key=True, unique=True, nullable=False)
    category = db.Column(db.String, default="Bookmarks")
    user_id = db.Column(db.Integer, ForeignKey('users.id', ondelete="CASCADE"))
    user = relationship("Users", backref="bookmarks")
    job_id = db.Column(db.Integer, ForeignKey('jobs.id', ondelete="CASCADE"))
    job = relationship("Jobs", backref="bookmarks")


class Tags(db.Model):
    """
    Tags Table in Database
    """
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True, unique=True, nullable=False)
    text = db.Column(db.String, nullable=False)
    jobs = relationship('Jobs', secondary=JobTag, back_populates='tags')


class Posts(db.Model):
    """
    Posts Table in Database
    """
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True, unique=True, nullable=False)
    user_id = db.Column(db.Integer, ForeignKey('users.id'))
    result_id = db.Column(db.Integer, ForeignKey('results.id'))
    public = db.Column(db.BOOLEAN, default=True)
    date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.utcnow)
    title = db.Column(db.String(64), nullable=False)


# parent
class Jobs(db.Model):
    """
    Jobs Table in Database
    """
    __tablename_ = 'jobs'
    id = db.Column(db.Integer, primary_key=True, unique=True, nullable=False)
    result = relationship("Results", backref="jobs", uselist=False)
    name = db.Column(db.String, nullable=False)
    tags = relationship('Tags', secondary=JobTag, back_populates='jobs')
    user_id = db.Column(db.Integer, ForeignKey('users.id'))
    user = relationship("Users", backref="jobs")
    video_uploaded = db.Column(db.Boolean, default=False)
    public = db.Column(db.Boolean, default=False, nullable=False)
    # Date updated
    date_updated = db.Column(db.TIMESTAMP, default=datetime.utcnow)


class Results(db.Model):
    __tablename_ = 'results'
    id = db.Column(db.Integer, ForeignKey('jobs.id'), primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('users.id'))
    result_code = db.Column(db.Enum(ResultCode), nullable=False, default=ResultCode.default)
    max_people = db.Column(db.Integer, default=0)
    date = db.Column(db.TIMESTAMP, default=datetime.utcnow, nullable=False)


"""
EVENT LISTENERS : Triggers a specific event (eg. jobs inserted -> result insert)
"""
@db.event.listens_for(Jobs, "after_insert")
def create_result(mapper, connection, target):
    """
    automatically creates a result when a job is inserted into database
    """
    re = Results.__table__
    connection.execute(re.insert().values(id=target.id, user_id=target.user_id))


@db.event.listens_for(Results, "after_insert")
def notify_observers(mapper, connection, target):
    """
    @deprecated, just for debugging
    """
    app.logger.debug("New waiting result was inserted. Notifying app.")
    # notify_analysis()


"""
EXCEPTIONS
"""


class JobDoesNotExist(HTTPException):
    """
    Exception: The job does not exist
    """
    code = 404
    description = "Job does not exist."


class JobFailedException(HTTPException):
    """
    Exception: The Job Failed
    """
    code = 404
    description = "Job failed."


class PersonIDRequired(HTTPException):
    """
    Exception: A person id is required
    """
    code = 400
    description = "Missing argument: Person ID"


class Forbidden(HTTPException):
    """
    Exception: Forbidden
    """
    code = 403
    description = "You are not allowed to do that."


def retrieve_job(job_id):
    """
    get a job and throw exception if it doesnt exist
    :param job_id: job id
    :return: job or exception
    """
    job = Jobs.query.get(job_id)
    if job is None:
        raise JobDoesNotExist()
    return job


def add_job(**kwargs):
    """
    add a job
    :param kwargs: job attributes
    :return: the new job object
    """
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
    """
    get all jobs by a user id
    :param user_id: user id
    :return: jobs as a list
    """
    jobs = db.session.query(Jobs).filter_by(user_id=user_id)
    return jobs


def get_results_by_user_id(user_id):
    """
    get all results by a given user
    :param user_id: user id
    :return: results as a list
    """
    jobs = db.session.query(Results).filter_by(user_id=user_id)
    return jobs


def get_result_by_job_id(job_id):
    """
    get results by a job id
    :param job_id: job id
    :return: result
    """
    return db.session.query(Results).filter_by(job_id=job_id).first()


def get_jobs_by_user_id(user_id, **kwargs):
    """
    get all jobs of a user
    :param user_id: id of the user
    :return: all jobs of the user
    """
    jobs = db.session.query(Jobs).filter_by(user_id=user_id).order_by(desc(Jobs.date_updated))
    if kwargs['result_code'] is not None:
        jobs = jobs.join(Results, Jobs.result).filter(
            Results.result_code == ResultCode(kwargs['result_code']))
    return jobs.all()


def serialize_array(ar):
    """
    serialize an array
    :param ar: array
    :return: serialized array
    """
    return [ob.serialize() for ob in ar]


def result_exists_for_job_id(job_id, result_type, person_id=None):
    """
    @deprecated
    check if a result already exists for a job id
    """
    return db.session.query(Results).filter_by(job_id=job_id, result_type=result_type, person_index=person_id)


def add_result(**kwargs):
    """
    Add a result to database
    """
    result = Results(id=kwargs['id'], user_id=kwargs['user_id'])
    db.session.add(result)
    db.session.commit()
    return result


class UserExists(werkzeug.exceptions.HTTPException):
    """
    Exception when a user exists
    """
    code = 409
    description = "Users already exists."


class UserDoesNotExist(HTTPException):
    """
    Exception when a user does not exist
    """
    code = 404
    description = "Users does not exist."


def add_user(username, password):
    """
    register a user
    :param username: username
    :param password: password of the user
    """
    existing = db.session.query(Users).filter_by(username=username).first()
    if existing is not None:
        raise UserExists()

    user = Users(username=username)
    user.hash_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def get_user(id):
    """
    get user object via user id
    :param id: user id
    :return: user object
    """
    user = Users.query.get(id)
    if not user:
        raise UserDoesNotExist()
    return user


def get_result_by_id(results_id):
    """
    get a result by its id
    :param results_id: result id
    :return: result by id
    """
    return Results.query.get(results_id)


def filter_results(user_id):
    """
    filter the results by user id
    :param user_id: user id
    :return: all results with a given user id
    """
    results = db.session.query(Results).filter_by(user_id=user_id).all()
    return results


def get_all_public_posts():
    """
    :return: all public posts
    """
    return db.session.query(Jobs).filter_by(public=True).order_by(desc(Jobs.date_updated)).all()


def get_pending_results():
    """
    @deprecated
    :return: all results that are pending
    """
    return db.session.query(Results).filter_by(result_code=ResultCode.waiting).order_by(asc(Results.date_updated))


def get_users():
    """
    get all users
    :return: all registered users
    """
    return Users.query.all()


def update_metadata(**kwargs):
    """
    update the metadata of a user
    :param kwargs: metadata as kwargs
    :return: metadata
    """
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
    """
    get a job by a job id
    :param id: job id
    :return: job object
    """
    return Jobs.query.get(id)


def get_job_by_result_id(id):
    """
    @deprecated
    get a job by the result id
    :param id:
    :return:
    """
    return db.session.query(Jobs).join(Results, Jobs.result).filter(Results.id == id).first()


def delete_job(id):
    """
    deletes a job by an id
    :param id: job id
    :return: if the job was deleted
    """
    db.session.query(Results).filter_by(id=id).delete()
    result = db.session.query(Jobs).filter_by(id=id).delete()
    return result > 0


class JobNotFinished(werkzeug.exceptions.HTTPException):
    """
    Exception when a job is not finished yet
    """
    code = 409
    description = "Job is not finished and cannot be posted."


def set_job_public(id, user_id):
    """
    post a job on the dashboard for a user
    :param id: job id
    :param user_id: user id
    :return: job object
    """
    job = retrieve_job(id)
    if get_result_by_id(id).result_code != ResultCode.success:
        raise JobNotFinished
    if job.user.id != user_id:
        raise Forbidden
    job.public = True
    db.session.commit()
    return job


def get_public_posts_filtered_by_tags(tags):
    """
    :param tags: tags
    :return: get all public jobs given filtered with tags array
    """
    t = db.session.query(Jobs).filter_by(public=True).filter(Jobs.tags.any(Tags.text.in_(tags)))
    return t.order_by(desc(Jobs.date_updated)).all()


def set_job_private(id, user_id):
    """
    removes a job from posts
    :param id: id of the job
    :param user_id: id of the user
    :return: job object
    """
    job = retrieve_job(id)
    if get_result_by_id(id).result_code != ResultCode.success:
        raise JobNotFinished
    if job.user.id != user_id:
        raise Forbidden
    job.public = False
    db.session.commit()
    return job


class BookmarkExists(werkzeug.exceptions.HTTPException):
    """
    Exception when a bookmark already exists
    """
    code = 409
    description = "Bookmark with given conditions already exists."


def save_bookmark(job_id, user_id, category):
    """
    save a job with given id in the users bookmarks
    :param job_id: job id of saved job
    :param user_id: user id
    :param category: optional category as string
    """
    if category is None:
        category = "Bookmarks"
    if db.session.query(Bookmarks).filter_by(job_id=job_id, user_id=user_id).scalar() is not None:
        raise BookmarkExists
    bookmark = Bookmarks(job_id=job_id, user_id=user_id, category=category)
    db.session.add(bookmark)
    db.session.commit()
    f = db.session.query(Jobs).filter_by(id=job_id).first()
    count = None
    if f is not None:
        count = len(f.bookmarks)
    else:
        raise JobDoesNotExist
    return {"count": count, "success": True}


def remove_bookmark(job_id, user_id, category):
    """
    remove a bookmark with a given job and user id
    :param job_id: job id
    :param user_id: user id
    :param category: optional category
    :return: success
    """
    if category is None:
        category = "Bookmarks"
    query = db.session.query(Bookmarks).filter_by(job_id=job_id, user_id=user_id)
    count = None
    result = query.delete()

    f = db.session.query(Jobs).filter_by(id=job_id).first()
    if f is not None:
        count = len(f.bookmarks)
    return {"count": count, "success": result > 0}


def get_bookmarks_by_user(id):
    """
    returns all bookmarks for a user
    :param id: user id
    :return:all bookmarks for a user
    """
    jobs = []
    bookmarks = db.session.query(Bookmarks).filter_by(user_id=id)
    for bookmark in bookmarks.all():
        jobs.append(bookmark.job)
    return jobs


def get_job_stats(user_id):
    """
    get job stats
    :param user_id: user id
    :return: number of failed jobs, number of pending jobs, number of successful jobs
    """
    jobs = db.session.query(Jobs).filter_by(user_id=user_id).order_by(desc(Jobs.date_updated))
    num_failed = jobs.join(Results, Jobs.result).filter(
        Results.result_code == ResultCode(-1)).count()
    num_pending = jobs.join(Results, Jobs.result).filter(
            Results.result_code == ResultCode(2)).count()
    num_pending += jobs.join(Results, Jobs.result).filter(
        Results.result_code == ResultCode(0)).count()
    num_success = jobs.join(Results, Jobs.result).filter(
        Results.result_code == ResultCode(1)).count()
    return {"failed": num_failed, "pending": num_pending, "success": num_success}


def delete_failed_jobs(user_id):
    """
    deletes all failed jobs of a user
    :param user_id: given user id
    :return:
    """
    results = db.session.query(Results).filter_by(user_id=user_id, result_code=ResultCode(-1))
    count = results.count()
    for r in results.all():
        db.session.query(Results).filter_by(id=r.id).delete()
        db.session.query(Jobs).filter_by(id=r.id).delete()
    results.delete()
    return count
