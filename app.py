from flask import Flask, render_template, request, redirect, url_for, flash
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from hashlib import sha256
import secrets
from datetime import datetime

import constants

app = Flask(__name__)
api = Api(app)
app.config['SECRET_KEY'] = constants.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql+psycopg2://{constants.DATABASE_USER}:' \
                                        f'{constants.DATABASE_PASSWORD}@' \
                                        f'{constants.DATABASE_HOST}/' \
                                        f'{constants.DATABASE_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)


class Token(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    commits = db.relationship('Commit', backref='token', lazy=True)

    def __repr__(self):
        return f'Token with id {self.id} was created at {self.created_at}'


class Commit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    token_id = db.Column(db.Integer, db.ForeignKey('token.id'), nullable=False)
    message = db.Column(db.String(255))

    def __repr__(self):
        return f'Commit with message {self.message} was created at {self.created_at}'


def generate_user_token(n):
    return secrets.token_urlsafe(n)


def generate_token_hash(token):
    return sha256(token.encode('utf-8')).hexdigest()


def check_if_token_exists(token, object):
    token_hash = generate_token_hash(token)
    q = Token.query.filter_by(token_hash=token_hash).first()
    return q is not None


@app.route('/')
def index():
    if request.args.get('token', 0):
        token = request.args['token']
        if check_if_token_exists(token, False):
            return redirect(url_for('rep', token=token))
        else:
            flash('Token not found')
    return render_template('index.html', title='Main')


@app.route('/generate')
def generate():
    token = generate_user_token(constants.TOKEN_BYTES_LENGTH)
    token_hash = generate_token_hash(token)
    t = Token(token_hash=token_hash)
    db.session.add(t)
    db.session.commit()
    return render_template('generate.html', title='Token generated', token=token)


@app.route('/rep/<token>')
def rep(token):
    if check_if_token_exists(token, False):
        return f'got into rep\ntoken: {token}'
    return 'token does not exist'
    # generate 404


class ApiGetRep(Resource):
    def get(self, token):
        return {'exists': check_if_token_exists(token, False)}

    def post(self, token):
        pass


class ApiCommit(Resource):
    def post(self, token):
        pass


api.add_resource(ApiGetRep, "/api/<string:token>")
api.add_resource((ApiCommit, "/api/<string:token>/commit"))

if __name__ == '__main__':
    app.run(debug=True)
