"""Application WSGI Python pour le formulaire de contact Coach OLOU.

Le site reste servi depuis dist/ et l’API ajoute un vrai traitement serveur :
validation, protection CSRF, honeypot, limitation de fréquence, stockage SQLite
et notification SMTP.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import smtplib
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import parse_qs, unquote


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "dist"
DATA_DIR = Path(os.environ.get("LEADS_DATA_DIR", str(ROOT / "data")))
DB_PATH = Path(os.environ.get("LEADS_DB_PATH", str(DATA_DIR / "leads.sqlite3")))
MAX_BODY_BYTES = 16_000
CSRF_MAX_AGE = 3_600
RATE_WINDOW = 900
RATE_LIMIT = 3

SUBJECTS = {
    "Personal branding & image",
    "Stratégie digitale & communication",
    "Cybersécurité & e-réputation",
    "Coaching & reconversion",
    "Conférence, formation ou intervention",
    "Production audiovisuelle & live streaming",
    "Partenariat ou autre projet",
}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; img-src 'self' data:; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; form-action 'self';"),
]


class RequestError(Exception):
    def __init__(self, status: str, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_response(start_response, status: str, payload: dict) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"), *SECURITY_HEADERS]
    start_response(status, headers)
    return [body]


def text_response(start_response, status: str, body: bytes, content_type: str, extra: list[tuple[str, str]] | None = None) -> list[bytes]:
    headers = [("Content-Type", content_type), ("Content-Length", str(len(body))), *SECURITY_HEADERS]
    if extra:
        headers.extend(extra)
    start_response(status, headers)
    return [body]


def secret() -> str:
    return os.environ.get("APP_SECRET", "")


def csrf_token() -> str:
    app_secret = secret()
    if len(app_secret) < 32:
        raise RequestError("503 Service Unavailable", "Le service de contact n’est pas encore configuré.")
    timestamp = str(int(time.time()))
    signature = hmac.new(app_secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def validate_csrf(token: str) -> None:
    app_secret = secret()
    if len(app_secret) < 32 or "." not in token:
        raise RequestError("403 Forbidden", "Session de formulaire invalide.")
    timestamp, signature = token.split(".", 1)
    try:
        issued_at = int(timestamp)
    except ValueError as error:
        raise RequestError("403 Forbidden", "Session de formulaire invalide.") from error
    if abs(time.time() - issued_at) > CSRF_MAX_AGE:
        raise RequestError("403 Forbidden", "Le formulaire a expiré. Rechargez la page.")
    expected = hmac.new(app_secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise RequestError("403 Forbidden", "Session de formulaire invalide.")


def read_request(environ: dict) -> dict:
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError as error:
        raise RequestError("400 Bad Request", "Requête invalide.") from error
    if length <= 0 or length > MAX_BODY_BYTES:
        raise RequestError("413 Request Entity Too Large", "Le formulaire est trop volumineux.")
    raw = environ["wsgi.input"].read(length)
    content_type = environ.get("CONTENT_TYPE", "").split(";", 1)[0].lower()
    try:
        if content_type == "application/json":
            data = json.loads(raw.decode("utf-8"))
        else:
            values = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
            data = {key: items[-1] if items else "" for key, items in values.items()}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RequestError("400 Bad Request", "Données de formulaire invalides.") from error
    if not isinstance(data, dict):
        raise RequestError("400 Bad Request", "Données de formulaire invalides.")
    return data


def clean(value: object, maximum: int) -> str:
    text = str(value or "").strip()
    if len(text) > maximum or CONTROL_RE.search(text):
        raise RequestError("422 Unprocessable Entity", "Un champ contient une valeur invalide.")
    return text


def validate_lead(data: dict) -> dict:
    if clean(data.get("website"), 200):
        raise RequestError("400 Bad Request", "Requête invalide.")
    lead = {
        "name": clean(data.get("name"), 120),
        "email": clean(data.get("email"), 180),
        "company": clean(data.get("company"), 180),
        "subject": clean(data.get("subject"), 80),
        "message": clean(data.get("message"), 5_000),
    }
    if not 2 <= len(lead["name"]) <= 120 or not EMAIL_RE.fullmatch(lead["email"]):
        raise RequestError("422 Unprocessable Entity", "Vérifiez votre nom et votre adresse email.")
    if lead["subject"] not in SUBJECTS or len(lead["message"]) < 10:
        raise RequestError("422 Unprocessable Entity", "Vérifiez le sujet et le contenu de votre message.")
    if data.get("consent") not in ("yes", True, "true", "on"):
        raise RequestError("422 Unprocessable Entity", "Votre consentement est nécessaire pour envoyer la demande.")
    return lead


def database() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        company TEXT NOT NULL,
        subject TEXT NOT NULL,
        message TEXT NOT NULL,
        ip_hash TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS rate_limits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_hash TEXT NOT NULL,
        created_at REAL NOT NULL
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_ip_time ON rate_limits(ip_hash, created_at)")
    connection.commit()
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass
    return connection


def ip_hash(environ: dict) -> str:
    address = environ.get("REMOTE_ADDR", "unknown")
    return hashlib.sha256(f"{secret()}:{address}".encode()).hexdigest()


def enforce_rate_limit(connection: sqlite3.Connection, address_hash: str) -> None:
    threshold = time.time() - RATE_WINDOW
    connection.execute("DELETE FROM rate_limits WHERE created_at < ?", (threshold,))
    count = connection.execute("SELECT COUNT(*) FROM rate_limits WHERE ip_hash = ?", (address_hash,)).fetchone()[0]
    if count >= RATE_LIMIT:
        connection.commit()
        raise RequestError("429 Too Many Requests", "Trop de demandes. Réessayez dans quelques minutes.")
    connection.execute("INSERT INTO rate_limits(ip_hash, created_at) VALUES (?, ?)", (address_hash, time.time()))


def save_lead(lead: dict, address_hash: str) -> None:
    connection = database()
    try:
        enforce_rate_limit(connection, address_hash)
        connection.execute("INSERT INTO leads(created_at, name, email, company, subject, message, ip_hash) VALUES (?, ?, ?, ?, ?, ?, ?)", (now_iso(), lead["name"], lead["email"], lead["company"], lead["subject"], lead["message"], address_hash))
        connection.commit()
    finally:
        connection.close()


def send_smtp(messages: list[EmailMessage]) -> bool:
    host = os.environ.get("SMTP_HOST", "")
    sender = os.environ.get("MAIL_FROM", os.environ.get("SMTP_USERNAME", ""))
    if not host or not sender:
        print("SMTP non configuré : prospect enregistré sans notification.", file=sys.stderr)
        return False
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no"}
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                if os.environ.get("SMTP_USERNAME"):
                    smtp.login(os.environ["SMTP_USERNAME"], os.environ.get("SMTP_PASSWORD", ""))
                for message in messages:
                    smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if os.environ.get("SMTP_USERNAME"):
                    smtp.login(os.environ["SMTP_USERNAME"], os.environ.get("SMTP_PASSWORD", ""))
                for message in messages:
                    smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException) as error:
        print(f"Échec notification SMTP : {error.__class__.__name__}", file=sys.stderr)
        return False


def send_notification(lead: dict) -> bool:
    sender = os.environ.get("MAIL_FROM", os.environ.get("SMTP_USERNAME", ""))
    recipient = os.environ.get("MAIL_TO", "euloge@oloustream.com")
    if not recipient:
        return False
    notification = EmailMessage()
    notification["Subject"] = f"Nouvelle demande — {lead['subject']}"
    notification["From"] = sender
    notification["To"] = recipient
    notification["Reply-To"] = lead["email"]
    notification.set_content(f"Nom : {lead['name']}\nEmail : {lead['email']}\nOrganisation : {lead['company'] or 'Non renseignée'}\nSujet : {lead['subject']}\n\n{lead['message']}")

    confirmation = EmailMessage()
    confirmation["Subject"] = "Nous avons bien reçu votre demande — Coach OLOU"
    confirmation["From"] = sender
    confirmation["To"] = lead["email"]
    confirmation.set_content(f"Bonjour {lead['name']},\n\nNous avons bien reçu votre demande concernant : {lead['subject']}.\n\nNous reviendrons vers vous rapidement.\n\nCoach OLOU\neuloge@oloustream.com")
    return send_smtp([notification, confirmation])


def check_origin(environ: dict) -> None:
    origin = environ.get("HTTP_ORIGIN", "")
    allowed = {item.strip().rstrip("/") for item in os.environ.get("ALLOWED_ORIGINS", "").split(",") if item.strip()}
    if origin and allowed and origin.rstrip("/") not in allowed:
        raise RequestError("403 Forbidden", "Origine non autorisée.")


def handle_contact(environ: dict, start_response) -> list[bytes]:
    try:
        check_origin(environ)
        data = read_request(environ)
        validate_csrf(str(data.get("csrf", "")))
        lead = validate_lead(data)
        address_hash = ip_hash(environ)
        save_lead(lead, address_hash)
        notified = send_notification(lead)
        message = "Votre demande a bien été enregistrée. Nous vous répondrons rapidement."
        if not notified:
            message = "Votre demande a bien été enregistrée. La notification email doit encore être configurée sur l’hébergement."
        return json_response(start_response, "201 Created", {"ok": True, "message": message})
    except RequestError as error:
        return json_response(start_response, error.status, {"ok": False, "message": error.message})
    except (OSError, sqlite3.Error):
        print("Erreur interne pendant le traitement du prospect.", file=sys.stderr)
        return json_response(start_response, "500 Internal Server Error", {"ok": False, "message": "Le service est temporairement indisponible. Écrivez directement à euloge@oloustream.com."})


def authorized(environ: dict) -> bool:
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(username, os.environ.get("ADMIN_USER", "")) and hmac.compare_digest(password, os.environ.get("ADMIN_PASSWORD", ""))


def handle_export(environ: dict, start_response) -> list[bytes]:
    if not os.environ.get("ADMIN_USER") or not os.environ.get("ADMIN_PASSWORD"):
        return json_response(start_response, "503 Service Unavailable", {"ok": False, "message": "Export prospects non configuré."})
    if not authorized(environ):
        return text_response(start_response, "401 Unauthorized", b"Authentification requise.", "text/plain; charset=utf-8", [("WWW-Authenticate", 'Basic realm="Prospects Coach OLOU"'), ("Cache-Control", "no-store")])
    connection = database()
    try:
        rows = connection.execute("SELECT created_at, name, email, company, subject, message FROM leads ORDER BY id DESC").fetchall()
    finally:
        connection.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "nom", "email", "organisation", "sujet", "message"])
    for row in rows:
        writer.writerow(row)
    return text_response(start_response, "200 OK", output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", [("Content-Disposition", 'attachment; filename="prospects-coach-olou.csv"'), ("Cache-Control", "no-store")])


def content_type(path: Path) -> str:
    return {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".png": "image/png"}.get(path.suffix.lower(), "application/octet-stream")


def serve_static(path: str, start_response) -> list[bytes]:
    relative = unquote(path.lstrip("/")) or "index.html"
    if relative.startswith(".") or "/." in relative or relative in {"_headers", ".htaccess"}:
        return text_response(start_response, "404 Not Found", b"Not found.", "text/plain; charset=utf-8")
    candidate = (STATIC_DIR / relative).resolve()
    if STATIC_DIR not in candidate.parents or not candidate.is_file():
        error_page = STATIC_DIR / "404.html"
        return text_response(start_response, "404 Not Found", error_page.read_bytes(), "text/html; charset=utf-8")
    return text_response(start_response, "200 OK", candidate.read_bytes(), content_type(candidate), [("Cache-Control", "public, max-age=3600")])


def application(environ: dict, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/") or "/"
    if path == "/api/contact-token" and method == "GET":
        try:
            return json_response(start_response, "200 OK", {"token": csrf_token()})
        except RequestError as error:
            return json_response(start_response, error.status, {"ok": False, "message": error.message})
    if path == "/api/contact" and method == "POST":
        return handle_contact(environ, start_response)
    if path == "/admin/leads.csv" and method == "GET":
        return handle_export(environ, start_response)
    if path.startswith("/api/") or path.startswith("/admin/"):
        return json_response(start_response, "405 Method Not Allowed", {"ok": False, "message": "Méthode non autorisée."})
    return serve_static(path, start_response)
