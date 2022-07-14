import json
import uuid
from enum import Enum, IntEnum
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound
from sqlalchemy.engine import CursorResult
from .db import engine


class InvalidToken(Exception):
    """指定されたtokenが不正だったときに投げる"""


# Enum
class LiveDifficulty(IntEnum):
    normal = 0
    hard = 1


class JoinRoomResult(IntEnum):
    Ok = 1  # 入場OK
    RoomFull = 2  # 満員
    Disbanded = 3  # 解散済み
    OtherError = 4  # その他エラー


class WaitRoomStatus(IntEnum):
    Waiting = 1  # ホストがライブ開始ボタン押すのを待っている
    LiveStart = 2  # ライブ画面遷移OK
    Dissolution = 3  # 解散された


class SafeUser(BaseModel):
    """token を含まないUser"""

    id: int
    name: str
    leader_card_id: int

    class Config:
        orm_mode = True


class RoomInfo(BaseModel):
    room_id: int
    live_id: int
    joined_user_count: int
    max_user_count: int

    class Config:
        orm_mode = True


class RoomUser(BaseModel):
    user_id :int
    name: str
    leader_card_id: int
    select_difficulty: LiveDifficulty

    class Config:
        orm_mode = True


class ResultUser(BaseModel):
    user_id :int
    judge_count_list :list[int]
    score: int

    class Config:
        orm_mode = True

def create_user(name: str, leader_card_id: int) -> str:
    """Create new user and returns their token"""
    token = str(uuid.uuid4())
    # NOTE: tokenが衝突したらリトライする必要がある.
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO `user` (name, token, leader_card_id) VALUES (:name, :token, :leader_card_id)"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
        # print(result)
    return token


def _get_user_by_token(conn, token: str) -> Optional[SafeUser]:
    result = conn.execute(
        text("SELECT `id`, `name`, `leader_card_id` FROM `user` WHERE `token`=:token"),
        dict(token=token),
    )
    try:
        row = result.one()
    except:
        return None
    return SafeUser.from_orm(row)


def get_user_by_token(token: str) -> Optional[SafeUser]:
    with engine.begin() as conn:
        return _get_user_by_token(conn, token)


def update_user(token: str, name: str, leader_card_id: int) -> None:
    # このコードを実装してもらう
    with engine.begin() as conn:
        # user = _get_user_by_token(token)

        result = conn.execute(
            text(
                "UPDATE `user` SET `name`=:name , `leader_card_id`=:leader_card_id WHERE `token`=:token"
            ),
            dict(token=token, name=name, leader_card_id=leader_card_id),
        )


def create_room(token: str, live_id: int, select_difficulty: int) -> int:
    with engine.begin() as conn:
        room_id = _create_room(conn=conn, live_id=live_id)
        join_room(conn=conn, token=token, room_id=room_id, select_difficulty=select_difficulty)
        return room_id

def _create_room(conn,live_id:int) -> int:
    # 部屋作成
    result = conn.execute(
        text(
            "INSERT INTO `room` (live_id) VALUES (:live_id)"
        ),
        {"live_id": live_id},
    )
    return result.lastrowid


def join_room(conn, token: str, room_id: int, select_difficulty: int):
    # ユーザid取得
    user_id = _get_user_by_token(conn=conn, token=token).id
    result = conn.execute(
        text(
            "INSERT INTO `room_member` (room_id , user_id , select_difficulty) VALUES (:room_id ,:user_id ,:select_difficulty)"
        ),
        {"room_id": room_id,"user_id":user_id,"select_difficulty":select_difficulty},
    )

def find_room(live_id :int)-> list[RoomInfo]:
    with engine.begin() as conn:
        if live_id == 0:
            where = ""
        else:
            where = " WHERE live_id=:live_id"

        result :CursorResult= conn.execute(
            text(
                "SELECT room_id, live_id, joined_user_count FROM room LEFT JOIN (SELECT room_id, COUNT(room_id) as joined_user_count FROM room_member GROUP BY room_id) as Cnt on room.id = joined_user_count"
                + where
            ),
            {"live_id": live_id}
        )
        try:
            roomrows = result.all()
        except NoResultFound:
            return  []

        roominfolist:list[RoomInfo] = [
            RoomInfo(room_id=row.room_id, live_id=row.live_id,joined_user_count=row.joined_user_count,max_user_count = 4 ) 
            for row in roomrows if row.joined_user_count
            ]

        return roominfolist
