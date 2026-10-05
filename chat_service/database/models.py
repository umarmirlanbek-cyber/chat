from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, UniqueConstraint, Index
from chat_service.database.db import Base


def now():
    return datetime.now(timezone.utc)


class Chat(Base):
    __tablename__ = 'chat'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    is_group = Column(Boolean, default=False)
    created_by = Column(Integer)
    created_date = Column(DateTime(timezone=True), default=now)


class ChatMember(Base):
    __tablename__ = 'chat_member'
    __table_args__ = (UniqueConstraint('chat_id', 'user_id'),)

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chat.id', ondelete='CASCADE'))
    user_id = Column(Integer, index=True)
    is_admin = Column(Boolean, default=False)
    last_read_message_id = Column(Integer, default=0)
    joined_date = Column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = 'message'
    __table_args__ = (Index('ix_message_chat_id_id', 'chat_id', 'id'),)

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chat.id', ondelete='CASCADE'))
    sender_id = Column(Integer)
    message_type = Column(String(20), default='text')
    text = Column(Text)
    file_url = Column(String(500))
    file_name = Column(String(255))
    file_size = Column(Integer)
    duration_seconds = Column(Float)
    reply_to_id = Column(Integer, ForeignKey('message.id', ondelete='SET NULL'))
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_date = Column(DateTime(timezone=True), default=now)
