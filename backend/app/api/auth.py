from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.username == payload.username).first()

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password.",
    )

    if user is None or not user.is_active:
        raise invalid_credentials

    if not verify_password(payload.password, user.hashed_password):
        raise invalid_credentials

    # The role chosen on the login form is never trusted by itself. It must
    # match the role already stored for this user in the database, otherwise
    # the request is rejected outright — selecting "ADMIN" in a dropdown must
    # never be sufficient to become an admin.
    if payload.role != user.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Selected role does not match this account's role.",
        )

    token = create_access_token(subject=user.username, role=user.role.value)

    return LoginResponse(
        access_token=token,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        department=user.department.name if user.department else None,
    )


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        department=user.department.name if user.department else None,
    )
