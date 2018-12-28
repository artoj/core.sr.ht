from srht.config import cfg
from srht.oauth import OAuthError
import requests

metasrht = cfg("meta.sr.ht", "origin")

def delegated_exchange(token, client_id, client_secret, revocation_url):
    """
    Validates an OAuth token with meta.sr.ht and returns a tuple of
    meta.sr.ht's responses: token, profile. Raises an OAuthError if anything
    goes wrong.
    """
    try:
        r = requests.post("{}/oauth/token/{}".format(metasrht, token), json={
            "client_id": client_id,
            "client_secret": client_secret,
            "revocation_url": revocation_url
        })
        _token = r.json()
    except Exception as ex:
        print(ex)
        raise OAuthError("Temporary authentication failure", status=500)
    if r.status_code != 200:
        raise OAuthError(_token, status=r.status_code)
    try:
        r = requests.get("{}/api/user/profile".format(metasrht), headers={
            "Authorization": "token {}".format(token)
        })
        profile = r.json()
    except Exception as ex:
        print(ex)
        raise OAuthError("Temporary authentication failure", status=500)
    if r.status_code != 200:
        raise OAuthError(profile, status=r.status_code)
    return _token, profile
