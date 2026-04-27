"""
WhatsApp webhook endpoint via Twilio.

Twilio sends a POST request here whenever a WhatsApp message arrives.
We run it through the ConversationalOrchestrator and reply with TwiML.
"""
import os
from fastapi import APIRouter, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from app.orchestrator.conversational_orchestrator import ConversationalOrchestrator
from app.core.session_store import session_store

router = APIRouter()


def _validate_twilio(request: Request, form_data: dict) -> bool:
    """Validates that the request genuinely came from Twilio."""
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        return True  # Skip validation in dev if token not set
    validator = RequestValidator(auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    return validator.validate(url, form_data, signature)


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    form_data = dict(await request.form())

    # Optional signature validation
    if not _validate_twilio(request, form_data):
        return Response(content="Forbidden", status_code=403)

    incoming_msg = form_data.get("Body", "").strip()
    from_number  = form_data.get("From", "")   # e.g. "whatsapp:+972501234567"

    twiml = MessagingResponse()

    if not incoming_msg:
        twiml.message("I didn't receive any text. Please send a message.")
        return Response(content=str(twiml), media_type="application/xml")

    # Get or create a persistent session for this phone number
    session_id = session_store.get_or_create_by_phone(from_number)

    try:
        orchestrator = ConversationalOrchestrator()
        result = orchestrator.run(session_id=session_id, user_message=incoming_msg)
        reply = result.get("assistant_message", "Sorry, something went wrong.")
    except Exception as e:
        reply = "Something went wrong on my end. Try again in a moment."

    # WhatsApp messages have a 1600-character limit
    if len(reply) > 1600:
        reply = reply[:1597] + "..."

    twiml.message(reply)
    return Response(content=str(twiml), media_type="application/xml")
