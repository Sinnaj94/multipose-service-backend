from redis import Redis
import sqlite3
from config import my_config
import os
import jwt
import datetime as dt
from sqlite3 import OperationalError
import time
from app import db, app
from werkzeug.security import generate_password_hash, check_password_hash


# source: https://github.com/miguelgrinberg/REST-auth/blob/master/api.py (modified)
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(128))

    def hash_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_auth_token(self, expires_in=600):
        return jwt.encode(
            {'id': self.id, 'exp': time.time() + expires_in},
            app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_auth_token(token):
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'],
                              algorithms=['HS256'])
        except:
            return
        return User.query.get(data['id'])


# create db
db.create_all()


def add_user(username, password):
    user = User(username=username)
    user.hash_password(password)
    db.session.add(user)
    db.session.commit()
    return 201

