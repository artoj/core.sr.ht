from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import Message
from srht.config import cfg, cfgi
import smtplib
import pgpy

# TODO: move this into celery worker

site_key, _ = pgpy.PGPKey.from_file(cfg("mail", "pgp-privkey"))
smtp_host = cfg("mail", "smtp-host", default=None)
smtp_port = cfgi("mail", "smtp-port", default=None)
smtp_user = cfg("mail", "smtp-user", default=None)
smtp_password = cfg("mail", "smtp-password", default=None)

def send_email(body, to, subject, encrypt_key=None):
    if smtp_host == "":
        return
    smtp = smtplib.SMTP(smtp_host, smtp_port)
    smtp.ehlo()
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
        multipart['From'] = smtp_user
        multipart['To'] = to
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
        wrapped['From'] = smtp_user
        wrapped['To'] = to
        smtp.sendmail(smtp_user, [to], wrapped.as_string(unixfrom=True))
    smtp.quit()
