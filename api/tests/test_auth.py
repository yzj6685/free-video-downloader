from app.services.auth_service import AuthService, AuthStore


def test_auth_register_login_me_and_logout(tmp_path):
    service = AuthService(AuthStore(str(tmp_path / "auth.sqlite3")))

    registered = service.register("User@example.com", "password123")
    assert registered.user.email == "User@example.com"
    assert registered.token

    current = service.me(registered.token)
    assert current.email == "User@example.com"

    logged_in = service.login("User@example.com", "password123")
    assert logged_in.user.id == registered.user.id
    assert logged_in.token != registered.token

    service.logout(logged_in.token)
    try:
        service.me(logged_in.token)
    except Exception as exc:
        assert getattr(exc, "status_code") == 401
    else:
        raise AssertionError("Expected logged out token to be rejected")


def test_auth_rejects_duplicate_email(tmp_path):
    service = AuthService(AuthStore(str(tmp_path / "auth.sqlite3")))
    service.register("user@example.com", "password123")

    try:
        service.register("user@example.com", "password123")
    except Exception as exc:
        assert getattr(exc, "status_code") == 409
    else:
        raise AssertionError("Expected duplicate email to be rejected")


def test_auth_rejects_wrong_password(tmp_path):
    service = AuthService(AuthStore(str(tmp_path / "auth.sqlite3")))
    service.register("user@example.com", "password123")

    try:
        service.login("user@example.com", "wrong-password")
    except Exception as exc:
        assert getattr(exc, "status_code") == 401
    else:
        raise AssertionError("Expected wrong password to be rejected")
