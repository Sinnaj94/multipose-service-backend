# This file is used to securely run the server and build the database
from flask.cli import FlaskGroup
from rq import Connection, Worker

from project.app import app
import redis

from project.model import model

cli = FlaskGroup(app)


# expose command "run_worker" to start the worker in the background
@cli.command("run_worker")
def run_worker():
    redis_url = app.config["REDIS_URL"]
    redis_connection = redis.from_url(redis_url)
    with Connection(redis_connection):
        worker = Worker(app.config["QUEUES"])
        worker.work()


# expose command "create_db" to create initial database
@cli.command("create_db")
def create_db():
    print("Creating my database...")
    model.db.create_all()


if __name__ == "__main__":
    cli()
