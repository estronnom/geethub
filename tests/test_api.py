from werkzeug.datastructures import FileStorage
from flask import url_for
from copy import copy
import io

from app import generate_token, generate_user_token

t, token = generate_token()
commit = None


def test_token_existence(client):
    invalid_token = \
        'qwertyuiopasdfghjklzxcvbnm'
    response = client.get(f'/api/{token}')
    assert response.json['exists']
    response = client.get(f'/api/{invalid_token}')
    assert not response.json['exists']


def test_commit(client):
    with io.BytesIO() as file1, io.BytesIO() as file2:
        for _ in range(10):
            file1.write(generate_user_token(16).encode())
            file2.write(generate_user_token(16).encode())

        fine_response = client.post(url_for('api.commit', token=token), data={
            'message': 'test commit',
            'file1': FileStorage(stream=copy(file1), filename='file1.txt'),
            'file2': FileStorage(stream=copy(file2), filename='file2.txt')
        }, content_type='multipart/form-data')

        out_of_limit_response = client.post(url_for('api.commit',
                                                    token=token), data={
            'message': 'test commit' * 255,
            'file1': FileStorage(stream=copy(file1), filename='file1.txt'),
            'file2': FileStorage(stream=copy(file2), filename='file2.txt')
        }, content_type='multipart/form-data')

        no_files_response = client.post(url_for('api.commit',
                                                token=token),
                                        data={'message': 'test commit'},
                                        content_type='multipart/form-data')

        no_changes_response = client.post(url_for('api.commit',
                                                  token=token), data={
            'message': 'test commit',
            'file1': FileStorage(stream=copy(file1), filename='file1.txt'),
            'file2': FileStorage(stream=copy(file2), filename='file2.txt')
        }, content_type='multipart/form-data')

        apply_changes_response = client.post(url_for('api.commit',
                                                     token=token), data={
            'message': 'test commit',
            'file2': FileStorage(stream=io.BytesIO(b'abcdefg'),
                                 filename='file1.txt')
        }, content_type='multipart/form-data')

        assert fine_response.status_code == 201
        assert out_of_limit_response.status_code == 412
        assert no_files_response == 400 and\
               no_files_response.json['message'] ==\
               'No files provided to commit'
        assert no_changes_response == 409
        assert apply_changes_response == 201


def test_list(client):
    fine_response = client.get(url_for('api.list', token=token))
    assert fine_response.status_code == 200\
           and len(list(fine_response.json.items())) == 2


def test_pull(client):
    empty_t, empty_token = generate_token()
    empty_repository_response = \
        client.get(url_for('api.pull', token=empty_token))
    assert empty_repository_response.status_code == 204
    fine_response = client.get(url_for('api.pull', token=token))
    assert fine_response.status_code == 200


def test_checkout(client):
    list_response = client.get(url_for('api.list', token=token))
    global commit
    commit = list(list_response.json.keys())[-1]
    checkout_response = \
        client.get(url_for('api.checkout', token=token, commit=commit))
    assert checkout_response.status_code == 200


def test_commit_delete(client):
    commit_delete_response = \
        client.delete(url_for('api.delete', token=token, commit=commit))
    assert commit_delete_response.status_code == 204


def test_token_delete(client):
    total_delete_response = \
        client.delete(url_for('api.totaldelete', token=token))
    assert total_delete_response.status_code == 204
