from flask import Flask, render_template, request, redirect, url_for, flash
from flask_restful import Api, Resource, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from hashlib import sha256
import secrets
from datetime import datetime
from werkzeug.utils import secure_filename

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
    message = db.Column(db.String(constants.COMMIT_MESSAGE_LENGTH))

    def __repr__(self):
        return f'Commit with message {self.message} was created at {self.created_at}'


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commit_id = db.Column(db.Integer, db.ForeignKey('commit.id'), nullable=False)
    filename = db.Column(db.String(128), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)


def generate_user_token(n):
    return secrets.token_urlsafe(n)


def generate_token_hash(token):
    return sha256(token.encode('utf-8')).hexdigest()


def check_if_token_exists(token, obj):
    token_hash = generate_token_hash(token)
    t = Token.query.filter_by(token_hash=token_hash).first()
    if obj:
        return t, t is not None
    else:
        return t is not None


def abort_if_token_nonexistent(token):
    if not check_if_token_exists(token, False):
        abort(404, message='Token does not exist')


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
    abort_if_token_nonexistent(token)
    return f'got into rep\ntoken: {token}'


class ApiGetRep(Resource):
    def get(self, token):
        return {'exists': check_if_token_exists(token, False)}


'''
commit_args = reqparse.RequestParser()
commit_args.add_argument('message', type=str, help='There must be a commit note')
commit_args.add_argument('files', type=datastructures.FileStorage, location='files')'''


class ApiCommit(Resource):
    def post(self, token):
        t, exists = check_if_token_exists(token, True)
        if not exists:
            abort(404, message='Token does not exist')
        message = request.form.get('message', '')
        if len(message) > constants.COMMIT_MESSAGE_LENGTH:
            abort(412, message='Commit message must be no longer than 255 letters')
        c = Commit(token=t, message=message)
        if not request.files:
            abort(400, message='No files provided to commit')
        for file in request.files:
            file = secure_filename(request.files[file])
            print(file.filename)


api.add_resource(ApiGetRep, "/api/<string:token>")
api.add_resource(ApiCommit, "/api/<string:token>/commit")

if __name__ == '__main__':
    app.run(debug=True)
