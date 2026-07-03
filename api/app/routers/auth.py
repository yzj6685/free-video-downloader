from fastapi import APIRouter, Header, Response

from app.models import AuthRequest, AuthResponse, UserResponse
from app.services.auth_service import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    return authorization[len(prefix) :].strip()


@router.post("/register", response_model=AuthResponse)
def register(payload: AuthRequest) -> AuthResponse:
    return auth_service.register(payload.email, payload.password)


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthRequest) -> AuthResponse:
    return auth_service.login(payload.email, payload.password)


@router.get("/me", response_model=UserResponse)
def me(authorization: str | None = Header(default=None)) -> UserResponse:
    return auth_service.me(bearer_token(authorization))


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)) -> Response:
    auth_service.logout(bearer_token(authorization))
    return Response(status_code=204)
