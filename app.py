from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_restful import Api, Resource, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from datetime import datetime
from hashlib import sha256
import secrets
import io

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
    files = db.relationship('File', backref='commit', lazy=True)

    # TODO: implement commit SHA
    def __repr__(self):
        return f'Commit with message {self.message} was created at {self.created_at}'


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commit_id = db.Column(db.Integer, db.ForeignKey('commit.id'), nullable=False)
    filename = db.Column(db.String(128), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)

    # TODO: implement file hash
    def __repr__(self):
        return f'File with name {self.filename} was created at {self.commit.created_at}'


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
    t, exists = check_if_token_exists(token, True)
    if not exists:
        abort(404, message='Token does not exist')
    c = db.session.query(func.max(File.id), File.filename, func.max(Commit.created_at)).join(Commit).filter_by(
        token=t).group_by(
        File.filename).order_by(File.filename).all()
    commits = []
    for item in c:
        file_id = item[0]
        m = db.session.query(Commit.message).join(File).filter_by(id=file_id).first()
        m = m[0].strip()
        commits.append(tuple(list(item) + [m]))
    return render_template('rep.html', title='Explore repo', token=token, commits=commits)


@app.route('/rep/<token>/<filename>')
def file_preview(token, filename):
    t, exists = check_if_token_exists(token, True)
    # TODO: create a function that either returns token object either aborts request
    if not exists:
        abort(404, message='Token does not exist')
    data = db.session.query(File.data).filter_by(filename=filename).join(Commit).filter_by(token=t).first()
    return send_file(io.BytesIO(data.data), mimetype='image/png')


class ApiGetRep(Resource):
    def get(self, token):
        return {'exists': check_if_token_exists(token, False)}


class ApiCommit(Resource):
    def post(self, token):
        t, exists = check_if_token_exists(token, True)
        if not exists:
            abort(404, message='Token does not exist')
        message = request.form.get('message', '')
        if len(message) > constants.COMMIT_MESSAGE_LENGTH:
            abort(412, message='Commit message must be no longer than 255 letters')
        if not request.files:
            abort(400, message='No files provided to commit')
        c = Commit(token=t, message=message)
        db.session.add(c)
        db.session.commit()  # commiting to get commit id
        try:
            for file in request.files:
                file = request.files[file]
                filename = secure_filename(file.filename)
                file_handle = file.stream.read()
                f = File(commit=c, filename=filename, data=file_handle)
                db.session.add(f)
        except SQLAlchemyError as exc:
            # TODO: implement logging
            print(exc)
            db.session.rollback()
            db.session.delete(c)
        db.session.commit()
        return {"message": "OK"}, 201


api.add_resource(ApiGetRep, "/api/<string:token>")
api.add_resource(ApiCommit, "/api/<string:token>/commit")

if __name__ == '__main__':
    app.run(debug=True)
