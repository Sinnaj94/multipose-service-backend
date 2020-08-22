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
    CREATE TABLE IF NOT EXISTS analysis_2d (
    video_id text PRIMARY KEY,
    user_id text NOT NULL,
    date_started timestamp default null,
    date_ended timestamp default null,
    num_people integer default null,
    data text default null,
    result_code integer default null
    )
    """
    cur.execute(create)
    conn.commit()


# todo: exceptions
def add_video(video_id, user_id):
    cur = conn.cursor()
    add = """
    INSERT INTO analysis_2d (video_id, user_id) values (?, ?);
    """
    cur.execute(add, (video_id, user_id))
    conn.commit()


def start_analysis(video_id, user_id):
    cur = conn.cursor()
    set = """
    UPDATE analysis_2d
    SET date_started = ?,
        user_id = ?
    WHERE video_id = ?;
    """
    cur.execute(set, (dt.datetime.now(), user_id, video_id))
    if cur.rowcount == 0:
        raise OperationalError("ID %s was not found" % video_id)
    conn.commit()


def is_started(video_id, user_id):
    cur = conn.cursor()
    statement = """
    SELECT *
    FROM analysis_2d
    WHERE video_id = ?
    AND user_id = ?
    AND date_started IS NOT NULL
    """
    cur.execute(statement, (video_id, user_id))
    return cur.fetchone() is not None


def is_finished(video_id, user_id):
    cur = conn.cursor()
    statement = """
    SELECT *
    FROM analysis_2d
    WHERE video_id = ?
    AND user_id = ?
    AND date_ended IS NOT NULL
    """
    cur.execute(statement, (video_id, user_id))
    return cur.fetchone() is not None

