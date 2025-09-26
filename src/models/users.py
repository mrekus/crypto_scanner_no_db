import datetime
from enum import Enum

from sqlalchemy import Column, Integer, String, Enum as SqlEnum, DateTime

from core.database import BaseModel


class ROLE(Enum):
    USER = 0


class User(BaseModel):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    last_login = Column(DateTime, default=datetime.datetime.now(datetime.UTC))
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))
    role = Column(SqlEnum(ROLE, name='role'), nullable=False, default=ROLE.USER)
