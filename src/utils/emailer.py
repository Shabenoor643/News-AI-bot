# FILE: src/utils/emailer.py | PURPOSE: smtplib transporter factory and send wrapper
import os
import smtplib
from email.message import EmailMessage
from src.utils.logger import create_logger
from src.utils.observability import AgentTrace

logger = create_logger("emailer")

def get_transporter():
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    
    if port == 465:
        server = smtplib.SMTP_SSL(host, port)
    else:
        server = smtplib.SMTP(host, port)
        server.starttls()
        
    if user and password:
        server.login(user, password)
        
    return server

async def send_mail(mail_options: dict) -> dict:
    trace = AgentTrace(
        agent_name="email_service",
        action="send_email",
        input_summary=mail_options.get("subject", ""),
    )
    msg = EmailMessage()
    msg["Subject"] = mail_options.get("subject", "")
    msg["From"] = mail_options.get("from") or os.getenv("SMTP_USER", "")
    msg["To"] = mail_options.get("to", "")
    
    if "html" in mail_options:
        msg.set_content(mail_options.get("text", "HTML email"))
        msg.add_alternative(mail_options["html"], subtype="html")
    elif "text" in mail_options:
        msg.set_content(mail_options["text"])

    try:
        server = get_transporter()
        server.send_message(msg)
        server.quit()
        logger.info("Email sent", extra={
            "subject": mail_options.get("subject"),
            "to": mail_options.get("to")
        })
        trace.output_summary = f"{mail_options.get('to')} | {mail_options.get('subject')}"
        return {"status": "success"}
    except Exception as e:
        trace.fail(e)
        logger.error(f"Failed to send email: {e}")
        raise
    finally:
        await trace.flush()
