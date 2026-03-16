from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class OutlookOAuthState(Base, TimestampMixin):
    __tablename__ = "outlook_oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    state_token: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    default_project_name: Mapped[str] = mapped_column(String, nullable=False)
    source_folder_id: Mapped[str] = mapped_column(String, nullable=True)
