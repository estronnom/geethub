from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_restful import Api, Resource, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from datetime import datetime
from hashlib import sha256, sha1
import zlib
import zipfile
import mimetypes
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


def generate_user_token(n):
    return secrets.token_urlsafe(n)


def generate_token_hash(token):
    return sha256(token.encode('utf-8')).hexdigest()


def check_if_token_exists(token):
    token_hash = generate_token_hash(token)
    t = Token.query.filter_by(token_hash=token_hash).first()
    if t is None:
        return False
    else:
        return t


def abort_if_token_nonexistent(token):
    t = check_if_token_exists(token)
    if not t:
        abort(404, message='Token does not exist!')
    else:
        return t


def checkout_filelist(t, sha):
    created_at = db.session.query(Commit.created_at).filter_by(token=t).filter(
        Commit.hash.like(f'{sha}%')).first()
    c = db.session.query(func.max(File.id), File.filename, func.max(Commit.created_at)).join(Commit).filter_by(
        token=t).filter(Commit.created_at <= created_at.created_at).group_by(
        File.filename).order_by(File.filename).all()
    return c


def pull_filelist(t):
    c = db.session.query(func.max(File.id), File.filename, func.max(Commit.created_at)).join(Commit).filter_by(
        token=t).group_by(
        File.filename).order_by(File.filename).all()
    return c


def generate_zip(filelist):
    with zipfile.ZipFile('Pull.zip', 'w') as zip_response:
        for file in filelist:
            file_bytes = File.query.filter_by(id=file[0]).first().data
            file_bytes = zlib.decompress(file_bytes)
            zip_response.writestr(file[1], file_bytes)
        return zip_response


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
    hash = db.Column(db.String(constants.COMMIT_MESSAGE_LENGTH))
    files = db.relationship('File', backref='commit', lazy=True)

    def __repr__(self):
        return f'Commit with message {self.message} was created at {self.created_at}'


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commit_id = db.Column(db.Integer, db.ForeignKey('commit.id'), nullable=False)
    filename = db.Column(db.String(128), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    hash = db.Column(db.String(40))

    def __repr__(self):
        return f'File with name {self.filename} was created at {self.commit.created_at}'


@app.route('/')
def index():
    if request.args.get('token', 0):
        token = request.args['token']
        if check_if_token_exists(token):
            return redirect(url_for('checkout', token=token))
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


@app.route('/<token>/commits/<sha>')
@app.route('/<token>')
def checkout(token, sha=None):
    t = abort_if_token_nonexistent(token)
    if sha:
        c = checkout_filelist(t, sha)
    else:
        c = pull_filelist(t)
    if not c:
        return f'Your repository is empty<p>Upload some files via post request<p>Token: {token}'
    files = []
    for item in c:
        file_id = item[0]
        m = db.session.query(Commit.message).join(File).filter_by(id=file_id).first()
        m = m[0].strip()
        files.append(tuple(list(item) + [m]))
    last_commit = Commit.query.filter_by(token=t).order_by(Commit.created_at.desc()).first()
    last_commit_hash = last_commit.hash[:constants.HASH_OFFSET]
    return render_template('rep.html', title='Explore repository', token=token, commits=files,
                           last_commit_hash=sha if sha else last_commit_hash)


@app.route('/<token>/<filename>')
def file_preview(token, filename):
    t = abort_if_token_nonexistent(token)
    data = db.session.query(File.data).filter_by(filename=filename).join(Commit).filter_by(token=t).first()
    data = zlib.decompress(data.data)
    mimetype = mimetypes.guess_type(filename)[0]
    if mimetype.startswith('text'):
        mimetype = 'text/plain'
    return send_file(io.BytesIO(data), mimetype=mimetype)


@app.route('/<token>/commits')
def list_commits(token):
    t = abort_if_token_nonexistent(token)
    commits = Commit.query.filter_by(token=t).order_by(Commit.created_at.desc()).all()
    return render_template('commits.html', title='Commits list', token=token, commits=commits)


@app.errorhandler(404)
def not_found(exc):
    return make_response('Not found!', 404)


class ApiGetRep(Resource):
    def get(self, token):
        exists = check_if_token_exists(token)
        return {'exists': True if exists else exists}


class ApiCommit(Resource):
    def post(self, token):
        t = abort_if_token_nonexistent(token)
        message = request.form.get('message', '')
        if len(message) > constants.COMMIT_MESSAGE_LENGTH:
            abort(412, message='Commit message must be no longer than 255 letters')
        if not request.files:
            abort(400, message='No files provided to commit')
        c = Commit(token=t, message=message,
                   hash=generate_token_hash(generate_user_token(constants.TOKEN_BYTES_LENGTH)))
        db.session.add(c)
        # db.session.commit()  # commiting to get commit id
        try:
            for file in request.files:
                file = request.files[file]
                filename = secure_filename(file.filename)
                file_handle = file.stream.read()
                file_hash = sha1(file_handle).hexdigest()
                f = db.session.query(File.hash).join(Commit).filter_by(token=t).filter(
                    File.filename == filename).order_by(
                    Commit.created_at.desc()).first()
                if f and f.hash == file_hash:
                    continue
                file_handle = zlib.compress(file_handle)
                f = File(commit=c, filename=filename, data=file_handle, hash=file_hash)
                db.session.add(f)
        except SQLAlchemyError as exc:
            # TODO: implement logging
            db.session.rollback()
            db.session.delete(c)
        db.session.commit()
        return {"message": "OK"}, 201


class ApiList(Resource):
    def get(self, token):
        t = abort_if_token_nonexistent(token)
        c = Commit.query.filter_by(token=t).all()
        if not c:
            return {'message': 'Repository is empty!'}, 404
        else:
            response_json = {}
        for commit in c:
            filelist = checkout_filelist(t, commit.hash)
            filelist = [file.filename for file in filelist]
            response_json[commit.hash] = {'message': commit.message, 'filelist': filelist}
        return response_json, 200


class ApiPull(Resource):
    def get(self, token):
        t = abort_if_token_nonexistent(token)
        filelist = pull_filelist(t)
        if not filelist:
            return {'message': 'Repository is empty!'}, 404
        zip_response = generate_zip(filelist)
        return send_file(zip_response, mimetype='application/zip')


class ApiCheckout(Resource):
    def get(self, token, commit):
        t = abort_if_token_nonexistent(token)
        filelist = checkout_filelist(t, commit)
        if not filelist:
            return {'message': 'Repository is empty!'}, 404
        zip_response = generate_zip(filelist)
        return send_file(zip_response, mimetype='application/zip')


api.add_resource(ApiGetRep, "/api/<string:token>")
api.add_resource(ApiCommit, "/api/<string:token>/commit")
api.add_resource(ApiList, "/api/<string:token>/list")
api.add_resource(ApiPull, "/api/<string:token>/pull")
api.add_resource(ApiCheckout, "/api/<string:token>/checkout/<string:commit>")

if __name__ == '__main__':
    app.run(debug=True)
