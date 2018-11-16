from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import Message
from email.utils import formatdate
from flask import request, has_request_context, has_app_context, current_app
from srht.config import cfg, cfgi
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
error_to = cfg("mail", "error-to", default=None)
error_from = cfg("mail", "error-from", default=None)
meta_url = cfg("meta.sr.ht", "origin")

def lookup_key(user, oauth_token):
    """
    Looks up the preferred PGP key for the given username and their OAuth token.
    """
    # TODO: we should stash this somewhere and use webhooks to update it
    r = requests.get(meta_url + "/api/user/profile", headers={
        "Authorization": "token {}".format(oauth_token)
    })
    if r.status_code != 200:
        return None
    key_id = r.json()["use_pgp_key"]
    if key_id == None:
        return None
    r = requests.get(meta_url + "/api/pgp-key/{}".format(key_id))
    if r.status_code != 200:
        return None
    return r.json()["key"]

def send_email(body, to, subject, encrypt_key=None, **headers):
    if smtp_host == "":
        return
    smtp = smtplib.SMTP(smtp_host, smtp_port)
    smtp.ehlo()
    if smtp_user and smtp_password:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
    multipart = MIMEMultipart(_subtype="signed", micalg="pgp-sha1",
        protocol="application/pgp-signature")
    text_part = MIMEText(body)
    signature = str(site_key.sign(text_part.as_string().replace('\n', '\r\n')))
    sig_part = Message()
    sig_part['Content-Type'] = 'application/pgp-signature; name="signature.asc"'
    sig_part['Content-Description'] = 'OpenPGP digital signature'
    sig_part.set_payload(signature)
    multipart.attach(text_part)
    multipart.attach(sig_part)
    if not encrypt_key:
        multipart['Subject'] = subject
        if 'From' not in headers:
            multipart['From'] = smtp_from or smtp_user
        if 'To' not in headers:
            multipart['To'] = to
        if 'Date' not in headers:
            multipart['Date'] = formatdate()
        for key in headers:
            multipart[key] = headers[key]
        smtp.sendmail(smtp_user, [to], multipart.as_string(unixfrom=True))
    else:
        pubkey, _ = pgpy.PGPKey.from_blob(encrypt_key.replace('\r', '').encode())
        pgp_msg = pgpy.PGPMessage.new(multipart.as_string(unixfrom=True))
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
        wrapped['Subject'] = subject
        if 'From' not in headers:
            wrapped['From'] = smtp_from or smtp_user
        if 'To' not in headers:
            wrapped['To'] = to
        if 'Date' not in headers:
            wrapped['Date'] = formatdate()
        for key in headers:
            wrapped[key] = headers[key]
        smtp.sendmail(smtp_user, [to], wrapped.as_string(unixfrom=True))
    smtp.quit()

def mail_exception(ex):
    if not error_to or not error_from:
        print("Warning: no email configured for error emails")
        return
    try:
        data = request.get_data() or b"(no request body)"
    except:
        data = "(error getting request data)"
    try:
        data = data.decode()
    except:
        data = base64.b64encode(data)
    if "password" in data:
        data = "(request body contains password)"
    if has_request_context():
        body = f"""
Exception occured on {request.method} {request.url}

{traceback.format_exc()}

Request body:

{data}"""
    else:
        body = f"""
{traceback.format_exc()}"""
    if has_app_context():
        subject = f"[{current_app.site}] {ex.__class__.__name__}: {str(ex)}"
    else:
        subject = f"{ex.__class__.__name__} {str(ex)}"
    send_email(body, error_to, subject, **{"From": error_from})
