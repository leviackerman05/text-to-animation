from app.supabase_client import supabase, supabase_admin
from app.models import Message
import uuid

def create_chat(user_id: str, title: str, chat_id: str = None) -> str:
    """Creates a new chat for the user and returns the chat_id"""
    client = supabase_admin if supabase_admin else supabase
    
    data = {
        "user_id": user_id,
        "title": title
    }
    if chat_id:
        data["id"] = chat_id
        
    response = client.table("chats").insert(data).execute()
    return response.data[0]["id"]

def check_chat_exists(chat_id: str) -> bool:
    """Checks if a chat exists"""
    client = supabase_admin if supabase_admin else supabase
    try:
        response = client.table("chats").select("id").eq("id", chat_id).execute()
        return len(response.data) > 0
    except:
        return False

def add_message(chat_id: str, role: str, content: str, video_url: str = None):
    """Adds a message to the chat"""
    client = supabase_admin if supabase_admin else supabase
    
    message_data = {
        "chat_id": chat_id,
        "role": role,
        "content": content
    }
    if video_url:
        message_data["video_url"] = video_url
        
    client.table("messages").insert(message_data).execute()

def get_chat_history(chat_id: str):
    """Retrieves all messages for a specific chat"""
    client = supabase_admin if supabase_admin else supabase
    
    response = client.table("messages")\
        .select("*")\
        .eq("chat_id", chat_id)\
        .order("created_at")\
        .execute()
        
    return response.data

def get_user_chats(user_id: str):
    """Retrieves all chats for a user"""
    client = supabase_admin if supabase_admin else supabase
    
    response = client.table("chats")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()
        
    return response.data

def delete_chat(chat_id: str):
    """Deletes a chat and its messages (cascade)"""
    client = supabase_admin if supabase_admin else supabase
    
    client.table("chats").delete().eq("id", chat_id).execute()


def update_chat_title(chat_id: str, title: str):
    """Update chat title"""
    client = supabase_admin if supabase_admin else supabase
    client.table("chats").update({"title": title}).eq("id", chat_id).execute()
