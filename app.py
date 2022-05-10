from flask import Flask, render_template
from flask_restful import Api, Resource, reqparse, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from hashlib import sha256
import secrets

import constants

app = Flask(__name__)
api = Api(app)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql+psycopg2://{constants.DATABASE_USER}:' \
                                        f'{constants.DATABASE_PASSWORD}@' \
                                        f'{constants.DATABASE_HOST}/' \
                                        f'{constants.DATABASE_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)


class Tokens(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)


def generate_token(n):
    return secrets.token_urlsafe(n)


def generate_token_hash(token):
    return sha256(token.encode('utf-8')).hexdigest()


def check_if_token_exists(token):
    pass


@app.route('/')
def index():
    return render_template('index.html', title='Main')


@app.route('/generate')
def generate_token():
    return 'generate'


@app.route('/login')
def login():
    return 'login'


class GetRepo(Resource):
    def get(self, token):
        return {'data': token}

    def post(self, token):
        return {'data': token}


api.add_resource(GetRepo, "/<string:token>")

if __name__ == '__main__':
    app.run(debug=True)
