from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class CreatePrivateChatRequest(BaseModel):
    user_id: int


class CreateGroupRequest(BaseModel):
    name: str
    member_ids: List[int]


class RenameGroupRequest(BaseModel):
    name: str


class AddMemberRequest(BaseModel):
    user_id: int


class SendTextMessageRequest(BaseModel):
    text: str
    reply_to_id: Optional[int] = None


class EditMessageRequest(BaseModel):
    text: str


class MarkAsReadRequest(BaseModel):
    last_message_id: int


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    sender_id: int
    message_type: str
    text: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    duration_seconds: Optional[float] = None
    reply_to_id: Optional[int] = None
    is_edited: bool
    is_deleted: bool
    created_date: datetime


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    is_group: bool
    created_date: datetime


class ChatListItemResponse(BaseModel):
    id: int
    name: Optional[str] = None
    is_group: bool
    other_user_id: Optional[int] = None          # для личного чата: id собеседника
    last_message: Optional[MessageResponse] = None
    unread_count: int                            # сколько непрочитанных


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    is_admin: bool
    last_read_message_id: int        # по нему клиент рисует "прочитано" (синие галочки)
    joined_date: datetime
