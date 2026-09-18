"""
Announcement endpoints for the High School Management System API
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: str


def _require_teacher(teacher_username: str) -> Dict[str, Any]:
    """Ensure the given username belongs to a signed-in teacher/admin"""
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")
    return teacher


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail=f"Invalid {field_name}, expected YYYY-MM-DD")


def _validate_dates(start_date: Optional[str], expiration_date: str) -> None:
    expiration = _parse_date(expiration_date, "expiration_date")
    if start_date:
        start = _parse_date(start_date, "start_date")
        if start > expiration:
            raise HTTPException(
                status_code=400,
                detail="start_date must be on or before expiration_date")


def _to_object_id(announcement_id: str) -> ObjectId:
    try:
        return ObjectId(announcement_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid announcement id")


def _serialize(announcement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(announcement["_id"]),
        "message": announcement["message"],
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement["expiration_date"],
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements currently visible to everyone (public endpoint)"""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": today}},
        ],
    }
    announcements = announcements_collection.find(
        query).sort("expiration_date", 1)
    return [_serialize(a) for a in announcements]


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: str) -> List[Dict[str, Any]]:
    """Get all announcements for management - requires teacher authentication"""
    _require_teacher(teacher_username)
    announcements = announcements_collection.find().sort("expiration_date", 1)
    return [_serialize(a) for a in announcements]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    announcement: AnnouncementInput, teacher_username: str
) -> Dict[str, Any]:
    """Create a new announcement - requires teacher authentication"""
    _require_teacher(teacher_username)
    _validate_dates(announcement.start_date, announcement.expiration_date)

    try:
        result = announcements_collection.insert_one({
            "message": announcement.message,
            "start_date": announcement.start_date,
            "expiration_date": announcement.expiration_date,
        })
    except Exception:
        logger.exception("Failed to create announcement")
        raise HTTPException(
            status_code=500, detail="Failed to create announcement")

    created = announcements_collection.find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str, announcement: AnnouncementInput, teacher_username: str
) -> Dict[str, Any]:
    """Update an existing announcement - requires teacher authentication"""
    _require_teacher(teacher_username)
    _validate_dates(announcement.start_date, announcement.expiration_date)
    object_id = _to_object_id(announcement_id)

    try:
        result = announcements_collection.update_one(
            {"_id": object_id},
            {"$set": {
                "message": announcement.message,
                "start_date": announcement.start_date,
                "expiration_date": announcement.expiration_date,
            }}
        )
    except Exception:
        logger.exception("Failed to update announcement %s", announcement_id)
        raise HTTPException(
            status_code=500, detail="Failed to update announcement")

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": object_id})
    return _serialize(updated)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: str) -> Dict[str, Any]:
    """Delete an announcement - requires teacher authentication"""
    _require_teacher(teacher_username)
    object_id = _to_object_id(announcement_id)

    try:
        result = announcements_collection.delete_one({"_id": object_id})
    except Exception:
        logger.exception("Failed to delete announcement %s", announcement_id)
        raise HTTPException(
            status_code=500, detail="Failed to delete announcement")

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
