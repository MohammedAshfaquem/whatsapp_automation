"""Fallbacks for media we do not process yet, including voice messages."""


def generate_reply(message):
    kind = message.split(':', 1)[1].rstrip(']')
    return {
        'audio': 'I received your voice message, but cannot listen to audio here. Please type a short description, or choose Talk to team.',
        'video': 'I received your video, but cannot inspect it here. Please describe the issue, or choose Talk to team.',
    }.get(kind, 'This attachment is not supported here. Please type your message, or choose Talk to team.')
