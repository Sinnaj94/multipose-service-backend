from redis import Redis
import sqlite3
from config import my_config
import os
import datetime as dt
from sqlite3 import OperationalError

db_file = os.path.join(my_config['working_dir'], my_config['database_file'])
conn = sqlite3.connect(db_file, check_same_thread=False)


def create_table():
    cur = conn.cursor()
    create = """
    CREATE TABLE IF NOT EXISTS users (
    id text PRIMARY KEY,
    nickname text,
    password_hash text not null,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    cur.execute(create)
    conn.commit()