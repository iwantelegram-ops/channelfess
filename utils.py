"""Shared utility functions."""
from pyrogram import Client
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, PeerIdInvalid
from config import MAIN_CHANNEL_ID

async def check_membership(client: Client, user_id: int) -> bool:
    """Return True if user is a member/admin/creator of the main channel."""
    try:
        member = await client.get_chat_member(MAIN_CHANNEL_ID, user_id)
        return member.status.value in ("member", "administrator", "creator")
    except (UserNotParticipant, ChatAdminRequired, PeerIdInvalid, Exception):
        return False

def paginate(data: list, page: int, page_size: int = 15):
    """Return one page of data + total pages."""
    total = len(data)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    chunk = data[page * page_size : (page + 1) * page_size]
    return chunk, total_pages
