from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, Security, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.template import Template
from app.security import Principal, get_principal, require_write
from app.services.templating import extract_variables
from app.services.tenancy import scoped

router = APIRouter(
    prefix="/templates",
    tags=["Templates"],
    dependencies=[Depends(get_principal)],
)


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    channel: str = Field(..., min_length=1, max_length=20)
    subject_template: str | None = Field(default=None, max_length=255)
    body_template: str = Field(..., min_length=1, max_length=10000)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    channel: str | None = Field(default=None, max_length=20)
    subject_template: str | None = Field(default=None, max_length=255)
    body_template: str | None = Field(default=None, max_length=10000)


class TemplateRead(BaseModel):
    id: UUID
    client_id: UUID | None
    name: str
    channel: str
    subject_template: str | None
    body_template: str
    variables: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _to_read(t: Template) -> TemplateRead:
    var_source = f"{t.subject_template or ''} {t.body_template or ''}"
    variables = extract_variables(var_source)
    return TemplateRead(
        id=t.id,
        client_id=t.client_id,
        name=t.name,
        channel=t.channel,
        subject_template=t.subject_template,
        body_template=t.body_template,
        variables=variables,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED, dependencies=[Security(require_write)])
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    template = Template(
        workspace_id=principal.workspace_id,
        client_id=principal.client_id,
        name=payload.name,
        channel=payload.channel,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _to_read(template)


@router.get("", response_model=list[TemplateRead])
def list_templates(
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    stmt = scoped(select(Template), Template, principal).order_by(Template.created_at.desc())
    count_stmt = scoped(select(func.count(Template.id)), Template, principal)

    total = db.scalar(count_stmt) or 0
    response.headers["X-Total-Count"] = str(total)

    templates = db.execute(stmt).scalars().all()
    return [_to_read(t) for t in templates]


@router.get("/{id}", response_model=TemplateRead)
def get_template(
    id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    stmt = select(Template).where(Template.id == id, Template.workspace_id == principal.workspace_id)
    template = db.execute(stmt).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return _to_read(template)


@router.put("/{id}", response_model=TemplateRead, dependencies=[Security(require_write)])
def update_template(
    id: UUID,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    stmt = select(Template).where(Template.id == id, Template.workspace_id == principal.workspace_id)
    template = db.execute(stmt).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if payload.name is not None:
        template.name = payload.name
    if payload.channel is not None:
        template.channel = payload.channel
    if payload.subject_template is not None:
        template.subject_template = payload.subject_template
    if payload.body_template is not None:
        template.body_template = payload.body_template

    template.updated_at = func.now()
    db.commit()
    db.refresh(template)
    return _to_read(template)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Security(require_write)])
def delete_template(
    id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    stmt = select(Template).where(Template.id == id, Template.workspace_id == principal.workspace_id)
    template = db.execute(stmt).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    db.delete(template)
    db.commit()
    return None
