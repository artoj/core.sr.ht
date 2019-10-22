from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import abort, Response, request
from srht.config import cfg
import base64
import binascii
import json
import os

private_key = cfg("webhooks", "private-key")
private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(private_key))
public_key = private_key.public_key()

# TODO: Put nonces into redis and reject duplicates
def verify_request_signature(request):
    payload = request.data
    signature = request.headers.get("X-Payload-Signature")
    nonce = request.headers.get("X-Payload-Nonce")
    try:
        signature = base64.b64decode(signature)
        nonce = nonce.encode()
        public_key.verify(signature, payload + nonce)
        return payload
    except Exception as ex:
        print("Request signature payload verification failure")
        print(ex)
        abort(Response(
            status=403,
            mimetype="application/json",
            response=json.dumps({
                "errors": [
                    { "reason": "Request payload signature " +
                        "verification failed." },
                ]
            })))

def sign_payload(payload):
    nonce = binascii.hexlify(os.urandom(8))
    signature = private_key.sign(payload.encode() + nonce)
    signature = base64.b64encode(signature).decode()
    return {
        "X-Payload-Signature": signature,
        "X-Payload-Nonce": nonce.decode(),
    }
