"""Constraint CRUD router."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, require_scheduler
from app.models.constraint import Constraint
from app.schemas.constraint import ConstraintCreate, ConstraintRead, ConstraintUpdate

router = APIRouter(prefix="/constraints", tags=["constraints"])


@router.post("", response_model=ConstraintRead, status_code=201,
             dependencies=[Depends(require_scheduler)])
def create_constraint(payload: ConstraintCreate, db: Session = Depends(get_db)):
    obj = Constraint(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("", response_model=List[ConstraintRead],
            dependencies=[Depends(get_current_user)])
def list_constraints(db: Session = Depends(get_db)):
    return db.query(Constraint).order_by(Constraint.id).all()


@router.get("/{constraint_id}", response_model=ConstraintRead,
            dependencies=[Depends(get_current_user)])
def get_constraint(constraint_id: int, db: Session = Depends(get_db)):
    obj = db.get(Constraint, constraint_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Constraint not found")
    return obj


@router.patch("/{constraint_id}", response_model=ConstraintRead,
              dependencies=[Depends(require_scheduler)])
def update_constraint(constraint_id: int, payload: ConstraintUpdate, db: Session = Depends(get_db)):
    obj = db.get(Constraint, constraint_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Constraint not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{constraint_id}", status_code=204,
               dependencies=[Depends(require_scheduler)])
def delete_constraint(constraint_id: int, db: Session = Depends(get_db)):
    obj = db.get(Constraint, constraint_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Constraint not found")
    db.delete(obj)
    db.commit()
    return None
