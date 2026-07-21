"""Personality profile routes — GET/PUT ~/.tawn/personality/profile.yaml."""

from fastapi import APIRouter
from pydantic import BaseModel

from tawn.home import tawn_home
from tawn.model.personality import load_profile, save_profile

router = APIRouter()


class ProfileBody(BaseModel):
    name: str = ""
    role: str = ""
    focus: str = ""
    extra: dict[str, str] = {}


@router.get("/profile")
def get_profile():
    return load_profile(tawn_home())


@router.put("/profile")
def put_profile(body: ProfileBody):
    home = tawn_home()
    profile = {"name": body.name, "role": body.role, "focus": body.focus, **body.extra}
    save_profile(home, {k: v for k, v in profile.items() if v})
    return {"ok": True}
