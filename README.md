# geethub
Simple VCS application based on flask and postgresql. Works with hash 
functions, compression and REST API. Pytest is also implemented.

# REST API
#### Token existence
Once you've generated your repository token, you can check its existence 
via GET request to `/api/<token>`

#### Creating new commit
All your commit operations are going to proceed with the API. You don't 
have to 
manually check which files are changed and which are added. Instead of this 
you can commit all your files, geethub will take care of it and observe 
edits you've made.

Commit URL is `/api/<token>/commit`. You have to provide files with your 
request and can also specify commit message with the `message` request 
param. Request must be POST.

###### via CURL
```
curl http://geethub.collectivism.ovh/api/your_token/commit
-d @path/to/file1.txt 
-d @path/to/file2.png 
-d {"message": "test commit"}
```

###### via Python requests
```
import requests as r

with open('file1.txt', 'rb) as f1, open('file2.png', 'rb') as f2:
    url = "http://geethub.collectivism.ovh/api/your_token/commit"
    r.post(url,
            data={'message': 'test commit'},
            files={'file1': f1, 'file2': f2})
```

#### Getting list of commits in repository

To fetch list of all commits with nested files and current repository size 
you have to send GET request to `/api/<token>/list`

#### Pulling last commit of repository

To pull last repository commit you have to send GET request to 
`/api/<token>/pull` 

#### Checking out certain commit

To fetch certain commit you have to send GET request to 
`/api/<token>/checkout/<commit>`

#### Deleting commit

To delete some commit use DELETE request to `/api/<token>/delete/<commit>`

#### Deleting whole repository

To delete WHOLE repository use DELETE request to `/api/<token>/totally/delete/this/repository`

Warning: this action is IRREVERSIBLE
