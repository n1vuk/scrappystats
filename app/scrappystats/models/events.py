
from dataclasses import dataclass
from typing import Optional

@dataclass
class MemberJoined:
    member_id: str
    name: str
    timestamp: str

@dataclass
class MemberLeft:
    member_id: str
    name: str
    timestamp: str

@dataclass
class MemberRejoined:
    member_id: str
    name: str
    timestamp: str

@dataclass
class RankChanged:
    member_id: str
    old_rank: str
    new_rank: str
    timestamp: str

@dataclass
class LevelChanged:
    member_id: str
    old_level: int
    new_level: int
    timestamp: str

@dataclass
class NameChanged:
    member_id: str
    old_name: str
    new_name: str
    timestamp: str
