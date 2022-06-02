def test_token_existence(client):
    valid_token = \
        '3kCIVpD0twuhyY8ySYS_DADMguY70z12utD7rkDg4XJWx2RmeRO85YvuqAFoR8yGOHlN2DfUGXrBzY6pk2ttgg'
    invalid_token = \
        'qwertyuiopasdfghjklzxcvbnm'
    response = client.get(f'/api/{valid_token}')
    assert response.json['exists']
    response = client.get(f'/api/{invalid_token}')
    assert not response.json['exists']
