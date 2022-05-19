from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_restful import Api, Resource, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from flask_migrate import Migrate
from sqlalchemy.orm import make_transient
from werkzeug.utils import secure_filename
from datetime import datetime
from hashlib import sha256, sha1
import zlib
import zipfile
import mimetypes
import secrets
from math import ceil
import sys
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


def checkout_filelist(t, commit):
    created_at = db.session.query(Commit.created_at).filter_by(token=t).filter(
        Commit.hash.like(f'{commit}%')).first()
    c = db.session.query(func.max(File.id), File.filename, func.max(Commit.created_at)).join(Commit).filter_by(
        token=t).filter(Commit.created_at <= created_at.created_at).group_by(
        File.filename).order_by(File.filename).all()
    return c


def pull_filelist(t):
    c = db.session.query(func.max(File.id), File.filename, func.max(Commit.created_at)).join(Commit).filter_by(
        token=t).group_by(
        File.filename).order_by(File.filename).all()
    return c


def generate_zip(file_list, zip_name):
    with zipfile.ZipFile(zip_name, 'w') as zip_response:
        for file in file_list:
            file_bytes = File.query.filter_by(id=file[0]).first().data
            file_bytes = zlib.decompress(file_bytes)
            zip_response.writestr(file[1], file_bytes)
        return zip_response


def generate_token():
    token = generate_user_token(constants.TOKEN_BYTES_LENGTH)
    token_hash = generate_token_hash(token)
    t = Token(token_hash=token_hash)
    db.session.add(t)
    db.session.commit()
    return t, token


def update_token_size(token_object, files_to_add):
    new_size = sum((sys.getsizeof(item.data) for item in files_to_add))
    token_object.current_size = new_size
    db.session.commit()


def clone(t, commit):
    token_object, token_string = generate_token()
    initial_commit = Commit.query.filter_by(token=t).filter(
        Commit.hash.like(f"{commit}%")).first()
    new_commit = Commit(hash=generate_token_hash(generate_user_token(constants.TOKEN_BYTES_LENGTH)),
                        message=initial_commit.message, token_id=token_object.id)
    db.session.add(new_commit)
    db.session.commit()
    filelist = checkout_filelist(t, commit)
    files_to_add = []
    try:
        for file in filelist:
            file = File.query.filter_by(id=file[0]).first()
            db.session.expunge(file)
            make_transient(file)
            del file.id
            del file.parent_id
            file.commit_id = new_commit.id
            files_to_add.append(file)
    except SQLAlchemyError:
        db.session.delete(new_commit)
        db.session.commit()
        return 'Internal error', 500
    else:
        db.session.add_all(files_to_add)
        db.session.commit()
        update_token_size(token_object, files_to_add)
        return redirect(url_for('checkout', token=token_string, commit=new_commit.hash[:constants.HASH_OFFSET])), 302


def delete_commit(token_object, commit):
    commit_to_delete = Commit.query.filter_by(token=token_object).filter(Commit.hash.like(f"{commit}%")).first()
    files_to_delete = File.query.filter_by(commit=commit_to_delete).all()
    try:
        for file in files_to_delete:
            child_file = File.query.filter_by(parent_id=file.id).first()
            if child_file:
                child_file.parent_id = file.parent_id
            db.session.delete(file)
        db.session.delete(commit_to_delete)
    except SQLAlchemyError:
        db.session.rollback()
        return False
    else:
        db.session.commit()
        return True


def delete_token(token_object):
    commit_object = Commit.query.filter_by(token=token_object).all()
    try:
        for commit in commit_object:
            File.query.filter_by(commit=commit).delete()
            db.session.delete(commit)
        db.session.delete(token_object)
    except SQLAlchemyError as exc:
        print(exc)
        db.session.rollback()
        return False
    else:
        db.session.commit()
        return True


class Token(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    commits = db.relationship('Commit', backref='token', lazy=True)
    current_size = db.Column(db.BigInteger, default=0)

    def __repr__(self):
        return f'Token {self.__dict__}'


class Commit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    token_id = db.Column(db.Integer, db.ForeignKey('token.id'), nullable=False)
    message = db.Column(db.String(constants.COMMIT_MESSAGE_LENGTH))
    hash = db.Column(db.String(constants.COMMIT_MESSAGE_LENGTH))
    files = db.relationship('File', backref='commit', lazy=True)

    def __repr__(self):
        return f'Commit {self.__dict__}'


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commit_id = db.Column(db.Integer, db.ForeignKey('commit.id'), nullable=False)
    filename = db.Column(db.String(128), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    hash = db.Column(db.String(40))
    parent_id = db.Column(db.Integer)

    def __repr__(self):
        return f'File {" ".join([str(self.__dict__[key]) for key in self.__dict__.keys() if key != "data"])}'


@app.route('/')
def index():
    if request.args.get('token', 0):
        token = request.args['token']
        if check_if_token_exists(token):
            return redirect(url_for('bare_checkout', token=token))
        else:
            flash('Token not found')
    return render_template('index.html', title='Main')


@app.route('/generate')
def generate():
    t, token = generate_token()
    return render_template('generate.html', title='Token generated', token=token)


@app.route('/<token>/')
def bare_checkout(token):
    t = abort_if_token_nonexistent(token)
    sha = Commit.query.filter_by(token=t).order_by(Commit.created_at.desc()).first()
    if not sha:
        return redirect(url_for('list_commits', token=token))
    return redirect(url_for('checkout', token=token, commit=sha.hash[:constants.HASH_OFFSET]))


@app.route('/<token>/commits/<commit>', methods=['GET', 'POST'])
def checkout(token, commit):
    t = abort_if_token_nonexistent(token)
    if request.method == 'POST':
        if request.form.get('clone', False):
            return clone(t, commit)
        elif request.form.get('delete', False):
            if delete_commit(t, commit):
                return redirect(url_for('list_commits', token=token))
            else:
                return 'Internal error', 500
    c = checkout_filelist(t, commit)
    files = []
    for item in c:
        file_id = item[0]
        query = db.session.query(Commit, File).join(File).filter_by(id=file_id).first()
        files.append(tuple(list(item) + [query.Commit.message, query.File.parent_id]))
    last_commit = Commit.query.filter_by(token=t).order_by(Commit.created_at.desc()).first()
    last_commit_hash = last_commit.hash[:constants.HASH_OFFSET]
    return render_template('rep.html', title='Explore repository', token=token, files=files,
                           last_commit_hash=commit if commit else last_commit_hash, max_size=constants.MAX_REP_SIZE_MB,
                           size=ceil(t.current_size / (1024 * 1024)))


@app.route('/<token>/commits/<commit>/changes/<filename>')
def changes(token, commit, filename):
    t = abort_if_token_nonexistent(token)
    if not mimetypes.guess_type(filename)[0].startswith('text'):
        return 'Not a text file, differences cannot be shown', 500
    file_object = db.session.query(File).join(Commit).filter_by(token=t).filter(Commit.hash.like(f"{commit}%")).filter(
        File.filename == filename).order_by(Commit.created_at.desc()).first()
    if not file_object or not file_object.parent_id:
        abort(404, message='File not found or has no previous versions')
    parent_file_object = File.query.filter_by(id=file_object.parent_id).first()
    child_file_list = zlib.decompress(file_object.data).decode('utf-8').rstrip().split('\n')
    parent_file_list = zlib.decompress(parent_file_object.data).decode('utf-8').rstrip().split('\n')
    child_file_set = set(child_file_list)
    parent_file_set = set(parent_file_list)
    added_lines = child_file_set - parent_file_set
    gone_lines = parent_file_set - child_file_set
    child_greater = len(child_file_list) > len(parent_file_list)
    max_list = child_file_list if child_greater else parent_file_list
    max_set = added_lines if child_greater else gone_lines
    symbol = ' +++' if child_greater else ' ---'
    outcome = []
    last_index = 0
    child_appended = None
    for i in range(min(len(child_file_list), len(parent_file_list))):
        last_index = i
        child_line = child_file_list[i]
        parent_line = parent_file_list[i]
        if child_line == parent_line:
            outcome.append(child_line)
            # print('values are the same', child_line)
            continue
        if parent_line in gone_lines:
            outcome.append(parent_line + ' ---')
            # print('parent line in gone lines', parent_line)
        if child_line in added_lines:
            child_appended = child_line
            outcome.append(child_line + ' +++')
            # print('child line in added lines', child_line)
        if child_line in child_file_set and child_line != child_appended:
            outcome.append(child_line)
            # print('rest case', child_line)
    else:
        for i in range(last_index + 1, len(max_list)):
            line = max_list[i]
            if line in max_set:
                outcome.append(line + symbol)
            else:
                outcome.append(line)
    return '<p>'.join(outcome)


@app.route('/<token>/commits', methods=['GET', 'POST'])
def list_commits(token):
    t = abort_if_token_nonexistent(token)
    if request.method == 'POST':
        if request.form.get('delete_validation', False) and request.form['delete_validation'] == f"delete {token[:6]}":
            if delete_token(t):
                return redirect(url_for('index')), 302
            else:
                return 'Internal error...', 500
        else:
            flash('Wrong input! Not going to delete...')
    commits = Commit.query.filter_by(token=t).order_by(Commit.created_at.desc()).all()
    return render_template('commits.html', title='Commits list', token=token, commits=commits)


@app.route('/<token>/commits/<commit>/<filename>')
def file_preview(token, commit, filename):
    t = abort_if_token_nonexistent(token)
    data = File.query.join(Commit).filter_by(token=t).filter(Commit.hash.like(f"{commit}%")).first()
    if not data and not data.data:
        abort(404, message='File not found!')
    data = zlib.decompress(data.data)
    mimetype = mimetypes.guess_type(filename)[0]
    if mimetype.startswith('text'):
        mimetype = 'text/plain'
    return send_file(io.BytesIO(data), mimetype=mimetype)


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
        db.session.commit()
        file_list = []
        commit_size = 0
        response = None
        try:
            for file in request.files:
                parent_id = None
                file = request.files[file]
                filename = secure_filename(file.filename)
                file_handle = file.stream.read()
                file_hash = sha1(file_handle).hexdigest()
                f = db.session.query(File).join(Commit).filter_by(token=t).filter(
                    File.filename == filename).order_by(
                    Commit.created_at.desc()).first()
                if f and f.hash == file_hash:
                    continue
                if f and f.hash != file_hash:
                    parent_id = f.id
                file_handle = zlib.compress(file_handle)
                commit_size += sys.getsizeof(file_handle)
                f = File(commit=c, filename=filename, data=file_handle, hash=file_hash, parent_id=parent_id)
                file_list.append(f)
            new_size = t.current_size + commit_size
        except SQLAlchemyError:
            db.session.delete(c)
            response = ({"message": "Internal error"}, 500)
        else:
            if not file_list:
                db.session.delete(c)
                response = ({"message": "Commit was rejected, no new files or changed detected"}, 409)
            elif new_size > constants.MAX_REP_SIZE:
                db.session.delete(c)
                response = ({"message": "Repository size constraint is exceeded, delete some commits to proceed"}, 409)
            else:
                db.session.add_all(file_list)
                t.current_size = new_size
                response = ({"message": "OK"}, 201)
        finally:
            db.session.commit()
            return response


class ApiList(Resource):
    def get(self, token):
        t = abort_if_token_nonexistent(token)
        filelist = Commit.query.filter_by(token=t).all()
        if not filelist:
            return {'message': 'Repository is empty!'}, 404
        else:
            response_json = {}
        for commit in filelist:
            filelist = checkout_filelist(t, commit.hash)
            filelist = [file.filename for file in filelist]
            response_json[commit.hash] = {'message': commit.message, 'filelist': filelist}
        return response_json, 200


# noinspection PyTypeChecker
class ApiPull(Resource):
    def get(self, token):
        t = abort_if_token_nonexistent(token)
        filelist = pull_filelist(t)
        if not filelist:
            return {'message': 'Repository is empty!'}, 404
        zip_response = generate_zip(filelist, f'{token[:constants.HASH_OFFSET]}.zip')
        return send_file(zip_response, mimetype='application/zip')


# noinspection PyTypeChecker
class ApiCheckout(Resource):
    def get(self, token, commit):
        t = abort_if_token_nonexistent(token)
        filelist = checkout_filelist(t, commit)
        if not filelist:
            return {'message': 'Repository is empty!'}, 204
        zip_response = generate_zip(filelist, f'{token[:constants.HASH_OFFSET]}_{commit[:constants.HASH_OFFSET]}.zip')
        return send_file(zip_response, mimetype='application/zip')


class ApiDelete(Resource):
    def delete(self, token, commit):
        t = abort_if_token_nonexistent(token)
        if delete_commit(t, commit):
            return {"message": "OK"}, 204
        else:
            return {"message": "Internal error"}, 500


api.add_resource(ApiGetRep, "/api/<string:token>")
api.add_resource(ApiCommit, "/api/<string:token>/commit")
api.add_resource(ApiList, "/api/<string:token>/list")
api.add_resource(ApiPull, "/api/<string:token>/pull")
api.add_resource(ApiCheckout, "/api/<string:token>/checkout/<string:commit>")
api.add_resource(ApiDelete, "/api/<string:token>/delete/<string:commit>")

if __name__ == '__main__':
    app.run(debug=True)
