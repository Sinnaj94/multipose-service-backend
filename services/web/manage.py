from flask.cli import FlaskGroup
from rq import Connection, Worker

from project.app import app
import redis

from project.model import model

cli = FlaskGroup(app)


@cli.command("run_worker")
def run_worker():
    redis_url = app.config["REDIS_URL"]
    redis_connection = redis.from_url(redis_url)
    with Connection(redis_connection):
        worker = Worker(app.config["QUEUES"])
        worker.work()


if __name__ == "__main__":
    # TODO: Put this into "manager"
    cli()
