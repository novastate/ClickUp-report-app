from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date

class TeamMember(BaseModel):
    id: str
    username: str

class TeamCreate(BaseModel):
    name: str
    clickup_workspace_id: str = ""
    clickup_space_id: str
    clickup_folder_id: str
    metric_type: str = "task_count"
    capacity_mode: str = "individual"
    sprint_length_days: int = 14
    space_name: str | None = None
    members: list[TeamMember] = []

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    clickup_space_id: Optional[str] = None
    clickup_folder_id: Optional[str] = None
    metric_type: Optional[str] = None
    capacity_mode: Optional[str] = None
    sprint_length_days: Optional[int] = None
    members: Optional[list[TeamMember]] = None

class TeamOut(BaseModel):
    id: int
    name: str
    clickup_space_id: str
    clickup_folder_id: str
    metric_type: str
    sprint_length_days: int
    created_at: str
