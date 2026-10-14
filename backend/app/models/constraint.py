"""Constraint definition model (hard / soft)."""
from sqlalchemy import Column, Float, Integer, String, Text, JSON
from app.database import Base


class Constraint(Base):
    __tablename__ = "constraint"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(16), nullable=False, index=True)  # hard | soft
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    weight = Column(Float, nullable=False, default=1.0)  # penalty weight for soft constraints
    constraint_data = Column(JSON, nullable=False, default=dict)
