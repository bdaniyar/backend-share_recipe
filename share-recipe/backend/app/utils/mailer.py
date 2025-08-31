import asyncio
import base64
import os
import smtplib
from email.message import EmailMessage

from app.config.config import settings

# Update: support PNG/SVG, correct MIME type, robust path resolution


def _get_embedded_logo():
    # Allow override via env
    env_path = os.getenv("LOGO_FILE")
    # Compute repo root: backend/app/utils -> ../../.. -> share-recipe-frontend
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    candidates = [
        env_path if env_path else None,
        os.path.join(repo_root, "public", "logo.png"),
        os.path.join(repo_root, "public", "logo.svg"),
        os.path.join(repo_root, "src", "assets", "logo.png"),
        os.path.join(repo_root, "src", "assets", "logo.svg"),
    ]
    for p in filter(None, candidates):
        if os.path.exists(p):
            ext = os.path.splitext(p)[1].lower()
            mime = "image/png" if ext == ".png" else "image/svg+xml"
            try:
                with open(p, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                return f"data:{mime};base64,{encoded}"
            except Exception:
                break
    return ""


def _send_email_sync(
    email_to: str, subject: str, text_body: str, html_body: str | None = None
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = email_to
    if html_body:
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
    else:
        msg.set_content(text_body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


async def send_verification_code(email_to: str, code: str) -> None:
    subject = "Your verification code"
    text_body = (
        f"Your verification code is: {code}. It will expire in 5 minutes.\n"
        "If you didn't request this, you can ignore this email."
    )

    html_body = f"""
    <!doctype html>
    <html>
    <body style=\"background:#f7f7f7;margin:0;padding:0;\">
      <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f7f7f7;\">
        <tr>
          <td align=\"center\" style=\"padding:24px;\">
            <table width=\"600\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#ffffff;border-radius:12px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;\">
              <tr>
                <td style=\"background:#1E1E1E;padding:20px 24px;\" align=\"center\">
                  <img src=\"{_get_embedded_logo()}\" alt=\"share recipe\" width=\"140\" style=\"display:block;\"/>
                </td>
              </tr>
              <tr>
                <td style=\"padding:24px 24px 8px;color:#111827;font-size:20px;font-weight:600;\">Verify your email</td>
              </tr>
              <tr>
                <td style=\"padding:0 24px 16px;color:#4b5563;font-size:14px;line-height:1.6;\">
                  Use the verification code below to finish creating your account on <strong>share<span style=\"color:#F59E0B\">recipe</span></strong>. This code expires in <strong>5 minutes</strong>.
                </td>
              </tr>
              <tr>
                <td align=\"center\" style=\"padding:8px 24px 24px;\">
                  <div style=\"font-size:28px;letter-spacing:6px;color:#1E1E1E;background:#FEF3E2;border:1px solid #F59E0B;border-radius:10px;padding:16px 24px;display:inline-block;\">
                    {code}
                  </div>
                </td>
              </tr>
              <tr>
                <td style=\"padding:0 24px 8px;color:#4b5563;font-size:14px;line-height:1.6;\">
                  If you didn’t request this, you can safely ignore this email.
                </td>
              </tr>
              <tr>
                <td style=\"padding:0 24px 24px;color:#6b7280;font-size:12px;border-top:1px solid #e5e7eb;\">
                  Sent by share<span style=\"color:#F59E0B\">recipe</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    await asyncio.to_thread(_send_email_sync, email_to, subject, text_body, html_body)
