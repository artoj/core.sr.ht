"""
This module is responsible for cryptographic authorization and encryption for
communication between sr.ht services and each other, as well as the outside
world.
"""
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.fernet import Fernet, InvalidToken
from datetime import timedelta
from flask import abort, Response, request, current_app
from srht.config import cfg
import base64
import binascii
import json
import os

private_key = cfg("webhooks", "private-key")
private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(private_key))
public_key = private_key.public_key()
fernet = Fernet(cfg("sr.ht", "network-key"))

try:
    from srht.redis import redis
except:
    print("Warning: unable to initialize redis, nonce reuse will be possible")
    redis = type("Redis", tuple(), {
        "get": lambda *args, **kwargs: None,
        "setex": lambda *args, **kwargs: None,
    })

def verify_request_signature(request):
    """
    Verifies an HTTP request has a valid signature from the sr.ht webhook key.
    Returns the decoded, authenticated payload.
    """
    def fail():
        abort(Response(
            status=403,
            mimetype="application/json",
            response=json.dumps({
                "errors": [
                    { "reason": "Request payload signature " +
                        "verification failed." },
                ]
            })))
    payload = request.data
    signature = request.headers.get("X-Payload-Signature")
    nonce = request.headers.get("X-Payload-Nonce")
    nonce_key = f"sr.ht.signature-nonce.{nonce}"
    if redis.get(nonce_key):
        fail()
    redis.setex(nonce_key, timedelta(days=90), "1")
    try:
        signature = base64.b64decode(signature)
        nonce = nonce.encode()
        public_key.verify(signature, payload + nonce)
        return payload
    except Exception as ex:
        print("Request signature payload verification failure")
        print(ex)
        fail()

def verify_payload(payload, signature, nonce):
    try:
        payload = payload.encode()
        signature = base64.b64decode(signature)
        nonce = nonce.encode()
        public_key.verify(signature, payload + nonce)
        return payload
    except Exception as ex:
        return None

def sign_payload(payload):
    """
    Returns the signature headers for a payload signed with the sr.ht webhook
    key.
    """
    nonce = binascii.hexlify(os.urandom(8))
    signature = private_key.sign(payload.encode() + nonce)
    signature = base64.b64encode(signature).decode()
    return {
        "X-Payload-Signature": signature,
        "X-Payload-Nonce": nonce.decode(),
    }

def verify_encrypted_authorization(auth):
    """
    Verifies an X-Srht-Authorization header and returns the authenticated
    side-channel payload, which includes the authorized user and OAuth client
    ID. This is used for internal HTTP requests between sr.ht services.
    """
    try:
        auth = fernet.decrypt(auth.encode(), ttl=30)
    except InvalidToken:
        abort(Response(
            status=403,
            mimetype="application/json",
            response=json.dumps({
                { "reason": "Internal request authorization failed." },
            }),
        ))
    return json.loads(auth)

def encrypt_request_authorization(user=None, client_id=None):
    if not user and not client_id:
        from srht.oauth import current_user
        user = current_user
    """
    Returns request headers which can be used to authenticate an HTTP request
    to other sr.ht services. This is used for internal HTTP requests between
    sr.ht services.
    """
    auth = {
        "name": user.username if user else None,
        "client_id": "core.sr.ht",
        "node_id": "core.sr.ht legacy",
        "oauth_client_id": client_id if client_id else None,
    }
    auth = fernet.encrypt(json.dumps(auth).encode())
    return {
        "Authorization": f"Internal {auth.decode()}",
    }
