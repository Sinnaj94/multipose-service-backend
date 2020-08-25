from redis import Redis
import sqlite3
from config import my_config
import os
import datetime as dt
from sqlite3 import OperationalError
"""from app import db


class Analysis_2D(db.Model):
    __tablename_ = 'analysis_2d'
    id = db.Column"""