"""Photo understanding and the description request used when an image is unavailable."""
from ..gemini_service import GeminiChatService
from .text import build_contextual_prompt

PHOTO_UNAVAILABLE = ('I could not access this photo right now. Please resend it or describe the issue. '
                     'You can also choose Talk to team.')
ANALYSIS_UNAVAILABLE = ('I received your photo, but image analysis is unavailable right now. '
                        'Please describe the issue, or choose Talk to team.')


def generate_reply(customer_message, media_id, conversation):
    """Use the photo as evidence, with the shop's real services as context."""
    if not media_id:
        return PHOTO_UNAVAILABLE
    if not GeminiChatService.is_configured():
        return ANALYSIS_UNAVAILABLE

    from apps.whatsapp.whatsapp_client import WhatsAppClient
    image = WhatsAppClient.download_image(media_id)
    if not image:
        return PHOTO_UNAVAILABLE

    prompt = build_contextual_prompt(customer_message, conversation)
    prompt += ('\n\nInspect the attached customer photo using the PHOTOS rules. '
               f'Customer preferred language: {conversation.customer.preferred_language}.')
    reply = GeminiChatService.generate_reply(prompt, image_bytes=image[0], mime_type=image[1])
    return reply if reply and reply.strip() else ANALYSIS_UNAVAILABLE


