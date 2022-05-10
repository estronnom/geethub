from flask import Flask, render_template, request, redirect, url_for, flash
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from hashlib import sha256
import secrets

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


class Tokens(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)

    def __repr__(self):
        return f'{self.id} {self.token_hash}'


def generate_user_token(n):
    return secrets.token_urlsafe(n)


def generate_token_hash(token):
    return sha256(token.encode('utf-8')).hexdigest()


def check_if_token_exists(token):
    token_hash = generate_token_hash(token)
    q = Tokens.query.filter_by(token_hash=token_hash).first()
    return q is not None


@app.route('/')
def index():
    if request.args.get('token', 0):
        token = request.args['token']
        if check_if_token_exists(token):
            return redirect(url_for('rep', token=token))
        else:
            flash('Token not found')
    return render_template('index.html', title='Main')


@app.route('/generate')
def generate():
    token = generate_user_token(constants.TOKEN_BYTES_LENGTH)
    token_hash = generate_token_hash(token)
    t = Tokens(token_hash=token_hash)
    db.session.add(t)
    db.session.commit()
    return render_template('generate.html', title='Token generated', token=token)


@app.route('/rep/<token>')
def rep(token):
    if check_if_token_exists(token):
        return f'got into rep\ntoken: {token}'
    return 'token does not exist'


class GetRep(Resource):
    def get(self, token):
        return {'exists': check_if_token_exists(token)}

    def post(self, token):
        pass


api.add_resource(GetRep, "/api/<string:token>")

if __name__ == '__main__':
    app.run(debug=True)
