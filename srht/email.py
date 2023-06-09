from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import Message
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from flask import request, has_request_context, has_app_context, current_app
from srht.crypto import encrypt_request_authorization
from srht.config import cfg, cfgi, cfgb, get_origin
import base64
import smtplib
import pgpy
import requests
import traceback

site_key = cfg("mail", "pgp-privkey", default=None)
if site_key:
    site_key, _ = pgpy.PGPKey.from_file(site_key)
smtp_host = cfg("mail", "smtp-host", default=None)
smtp_port = cfgi("mail", "smtp-port", default=None)
smtp_user = cfg("mail", "smtp-user", default=None)
smtp_password = cfg("mail", "smtp-password", default=None)
smtp_from = cfg("mail", "smtp-from", default=None)
smtp_encryption = cfg("mail", "smtp-encryption", default=None)
error_to = cfg("mail", "error-to", default=None)
error_from = cfg("mail", "error-from", default=None)
meta_url = get_origin("meta.sr.ht")

def micalg_for(hash_alg):
    return {
        pgpy.constants.HashAlgorithm.MD5: "pgp-md5",
        pgpy.constants.HashAlgorithm.SHA1: "pgp-sha1",
        pgpy.constants.HashAlgorithm.RIPEMD160: "pgp-ripemd160",
        pgpy.constants.HashAlgorithm.SHA256: "pgp-sha256",
        pgpy.constants.HashAlgorithm.SHA384: "pgp-sha384",
        pgpy.constants.HashAlgorithm.SHA512: "pgp-sha512",
        pgpy.constants.HashAlgorithm.SHA224: "pgp-sha224",
    }[hash_alg]

def lookup_key(user):
    """
    Looks up the preferred PGP key for the given username and their OAuth token.
    """
    # TODO: we should stash this somewhere and use webhooks to update it
    r = requests.get(meta_url + "/api/user/profile",
            headers=encrypt_request_authorization(user))
    if r.status_code != 200:
        return None
    key_id = r.json()["use_pgp_key"]
    if key_id == None:
        return None
    r = requests.get(meta_url + "/api/pgp-key/{}".format(key_id))
    if r.status_code != 200:
        return None
    return r.json()["key"]

def format_headers(**headers):
    headers['From'] = formataddr(parseaddr(headers['From']))
    headers['To'] = formataddr(parseaddr(headers['To']))
    if 'Reply-To' in headers:
        headers['Reply-To'] = formataddr(parseaddr(headers['Reply-To']))
    return headers

def prepare_email(body, to, subject, encrypt_key=None, **headers):
    headers['Subject'] = subject
    headers.setdefault('From', smtp_from or smtp_user)
    headers.setdefault('To', to)
    headers.setdefault('Date', formatdate())
    headers.setdefault('Message-ID', make_msgid())
    headers = format_headers(**headers)

    text_part = MIMEText(body)

    if site_key:
        signature = site_key.sign(text_part.as_string().replace('\n', '\r\n'))
        sig_part = Message()
        sig_part['Content-Type'] = 'application/pgp-signature; name="signature.asc"'
        sig_part['Content-Description'] = 'OpenPGP digital signature'
        sig_part.set_payload(str(signature))

        multipart = MIMEMultipart(_subtype="signed",
                micalg=micalg_for(signature.hash_algorithm),
                protocol="application/pgp-signature")
        multipart.attach(text_part)
        multipart.attach(sig_part)
    else:
        multipart = MIMEMultipart()
        multipart.attach(text_part)

    if not encrypt_key:
        for key in headers:
            multipart[key] = headers[key]
        return multipart
    else:
        pubkey, _ = pgpy.PGPKey.from_blob(encrypt_key.replace('\r', '').encode())
        pgp_msg = pgpy.PGPMessage.new(multipart.as_string(unixfrom=False))
        if pubkey.get_uid(to):
            # https://github.com/SecurityInnovation/PGPy/issues/367
            encrypted = str(pubkey.encrypt(pgp_msg, user=to))
        else:
            encrypted = str(pubkey.encrypt(pgp_msg))
        ver_part = Message()
        ver_part['Content-Type'] = 'application/pgp-encrypted'
        ver_part.set_payload("Version: 1")
        enc_part = Message()
        enc_part['Content-Type'] = 'application/octet-stream; name="message.asc"'
        enc_part['Content-Description'] = 'OpenPGP encrypted message'
        enc_part.set_payload(encrypted)
        wrapped = MIMEMultipart(_subtype="encrypted", protocol="application/pgp-encrypted")
        wrapped.attach(ver_part)
        wrapped.attach(enc_part)
        for key in headers:
            wrapped[key] = headers[key]
        return wrapped


def start_smtp():
    if smtp_encryption == 'tls':
        smtp = smtplib.SMTP_SSL(smtp_host, smtp_port)
    else:
        smtp = smtplib.SMTP(smtp_host, smtp_port)
    smtp.ehlo()
    if smtp_encryption == 'starttls':
        smtp.starttls()
    if smtp_user and smtp_password:
        smtp.login(smtp_user, smtp_password)
    return smtp


def send_email(body, to, subject, encrypt_key=None, **headers):
    message = prepare_email(body, to, subject, encrypt_key, **headers)
    if not smtp_host:
        print("Not configured to send email. The email we tried to send was:")
        print(message)
        return
    smtp = start_smtp()
    smtp.send_message(message, smtp_from, [to])
    smtp.quit()

def mail_exception(ex, user=None, context=None):
    if not error_to or not error_from:
        print("Warning: no email configured for error emails")
        return
    if has_app_context() and has_request_context():
        data = request.get_data() or b"(no request body)"
    else:
        data = b"(no request body)"
    try:
        data = data.decode()
    except:
        data = base64.b64encode(data)
    if "password" in data:
        data = "(request body contains password)"
    if has_app_context() and has_request_context():
        headers = "\n".join(
            key + ": " + value for key, value in request.headers.items())
        body = f"""
Exception occured on {request.method} {request.url}

{traceback.format_exc()}

Request body:

{data}

Request headers:

{headers}

Current user:

{user}"""
    else:
        body = f"""
{traceback.format_exc()}"""
    if context:
        subject = f"[{context}] {ex.__class__.__name__}"
    elif has_app_context():
        subject = (f"[{current_app.site}] {ex.__class__.__name__} on " +
            f"{request.method} {request.url}")
    else:
        subject = f"{ex.__class__.__name__}"
    send_email(body, error_to, subject, **{"From": error_from})
