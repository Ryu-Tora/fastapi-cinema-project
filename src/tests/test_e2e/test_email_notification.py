from email_validator import validate_email, EmailNotValidError
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from validators import url as validate_url
import pytest
import httpx
from bs4 import BeautifulSoup

from database import (
    ActivationTokenModel,
    UserModel,
    RefreshTokenModel,
    PasswordResetTokenModel,
)


@pytest.mark.e2e
@pytest.mark.order(1)
@pytest.mark.asyncio
async def test_registration(
    e2e_client, reset_db_once_for_e2e, settings, seed_user_groups, e2e_db_session
):
    user_data = {"email": "test@mate.com", "password": "StrongPassword123!"}

    response = await e2e_client.post("/api/v1/accounts/register/", json=user_data)
    assert response.status_code == 201, f"Expected 201, got {response.status_code}"
    response_data = response.json()
    assert response_data["email"] == user_data["email"]

    mailhog_url = (
        f"http://{settings.EMAIL_HOST}:{settings.MAILHOG_API_PORT}/api/v2/messages"
    )
    async with httpx.AsyncClient() as client:
        mailhog_response = await client.get(mailhog_url)

    await e2e_db_session.commit()
    e2e_db_session.expire_all()

    assert (
        mailhog_response.status_code == 200
    ), f"MailHog API returned {mailhog_response.status_code}"
    messages = mailhog_response.json()["items"]
    assert len(messages) > 0, "No emails were sent!"

    email = messages[0]
    assert (
        email["Content"]["Headers"]["To"][0] == user_data["email"]
    ), "Email recipient does not match."

    email_html = email["Content"]["Body"]
    email_subject = email["Content"]["Headers"].get("Subject", [None])[0]
    assert (
        email_subject == "Account Activation"
    ), f"Expected subject 'Account Activation', but got '{email_subject}'"

    soup = BeautifulSoup(email_html, "html.parser")
    email_element = soup.find("strong", id="email")
    assert email_element is not None, "Email element with id 'email' not found!"
    try:
        validate_email(email_element.text)
    except EmailNotValidError as e:
        pytest.fail(f"The email link {email_element.text} is not valid: {e}")
    assert email_element.text == user_data["email"], "Email content does not match!"

    link_element = soup.find("a", id="link")
    assert link_element is not None, "Activation link element with id 'link' not found!"
    activation_url = link_element["href"]
    assert validate_url(activation_url), f"The URL '{activation_url}' is not valid!"


@pytest.mark.e2e
@pytest.mark.order(2)
@pytest.mark.asyncio
async def test_account_activation(e2e_client, settings, e2e_db_session):
    user_email = "test@mate.com"

    stmt = (
        select(ActivationTokenModel)
        .join(UserModel)
        .where(UserModel.email == user_email)
    )
    result = await e2e_db_session.execute(stmt)
    activation_token_record = result.scalars().first()
    assert (
        activation_token_record
    ), f"Activation token for email {user_email} not found!"
    token_value = activation_token_record.token

    activation_url = "/api/v1/accounts/activate/"
    response = await e2e_client.post(
        activation_url, json={"email": user_email, "token": token_value}
    )
    assert (
        response.status_code == 200
    ), f"Expected status code 200, got {response.status_code}"
    response_data = response.json()
    assert (
        response_data["message"] == "User account activated successfully."
    ), "Unexpected activation message!"

    await e2e_db_session.commit()

    stmt_user = select(UserModel).where(UserModel.email == user_email)
    result_user = await e2e_db_session.execute(stmt_user)
    activated_user = result_user.scalars().first()
    assert activated_user.is_active, f"User {user_email} is not active!"

    mailhog_url = (
        f"http://{settings.EMAIL_HOST}:{settings.MAILHOG_API_PORT}/api/v2/messages"
    )
    async with httpx.AsyncClient() as client:
        mailhog_response = await client.get(mailhog_url)
    assert mailhog_response.status_code == 200, "Failed to fetch emails from MailHog!"
    messages = mailhog_response.json()["items"]
    assert len(messages) > 0, "No emails were sent!"

    email = messages[0]
    assert (
        email["Content"]["Headers"]["To"][0] == user_email
    ), "Recipient email does not match!"
    email_subject = email["Content"]["Headers"].get("Subject", [None])[0]
    assert (
        email_subject == "Account Activated Successfully"
    ), f"Expected subject 'Account Activated Successfully', but got '{email_subject}'"

    email_html = email["Content"]["Body"]
    soup = BeautifulSoup(email_html, "html.parser")

    email_element = soup.find("strong", id="email")
    assert email_element is not None, "Email element with id 'email' not found!"
    try:
        validate_email(email_element.text)
    except EmailNotValidError as e:
        pytest.fail(f"The email link {email_element.text} is not valid: {e}")
    assert (
        email_element.text == user_email
    ), "Email content does not match the user's email!"

    link_element = soup.find("a", id="link")
    assert link_element is not None, "Login link element with id 'link' not found!"
    login_url = link_element["href"]
    assert validate_url(login_url), f"The URL '{login_url}' is not valid!"


@pytest.mark.e2e
@pytest.mark.order(3)
@pytest.mark.asyncio
async def test_user_login(e2e_client, e2e_db_session):
    user_data = {"email": "test@mate.com", "password": "StrongPassword123!"}

    login_url = "/api/v1/accounts/login/"
    response = await e2e_client.post(login_url, json=user_data)

    assert (
        response.status_code == 201
    ), f"Expected status code 201, got {response.status_code}"
    response_data = response.json()

    assert "access_token" in response_data, "Access token is missing in the response!"
    assert "refresh_token" in response_data, "Refresh token is missing in the response!"

    refresh_token = response_data["refresh_token"]

    stmt = (
        select(RefreshTokenModel)
        .options(joinedload(RefreshTokenModel.user))
        .where(RefreshTokenModel.token == refresh_token)
    )
    result = await e2e_db_session.execute(stmt)
    stored_token = result.scalars().first()

    assert stored_token is not None, "Refresh token was not stored in the database!"
    assert (
        stored_token.user.email == user_data["email"]
    ), "Refresh token is linked to the wrong user!"


@pytest.mark.e2e
@pytest.mark.order(4)
@pytest.mark.asyncio
async def test_request_password_reset(e2e_client, e2e_db_session, settings):
    user_email = "test@mate.com"
    reset_url = "/api/v1/accounts/password-reset/request/"

    response = await e2e_client.post(reset_url, json={"email": user_email})
    assert (
        response.status_code == 200
    ), f"Expected status code 200, got {response.status_code}"
    response_data = response.json()
    assert (
        response_data["message"]
        == "If you are registered, you will receive an email with instructions."
    )

    stmt = (
        select(PasswordResetTokenModel)
        .join(UserModel)
        .where(UserModel.email == user_email)
    )
    result = await e2e_db_session.execute(stmt)
    reset_token = result.scalars().first()
    assert reset_token, f"Password reset token for email {user_email} was not created!"

    mailhog_url = (
        f"http://{settings.EMAIL_HOST}:{settings.MAILHOG_API_PORT}/api/v2/messages"
    )
    async with httpx.AsyncClient() as client:
        mailhog_response = await client.get(mailhog_url)

    assert mailhog_response.status_code == 200, "Failed to fetch emails from MailHog!"
    messages = mailhog_response.json()["items"]
    assert len(messages) > 0, "No emails were sent!"

    email_data = messages[0]
    assert (
        email_data["Content"]["Headers"]["To"][0] == user_email
    ), "Recipient email does not match!"
    email_subject = email_data["Content"]["Headers"].get("Subject", [None])[0]
    assert (
        email_subject == "Password Reset Request"
    ), f"Expected subject 'Password Reset Request', but got '{email_subject}'"

    email_html = email_data["Content"]["Body"]
    soup = BeautifulSoup(email_html, "html.parser")

    email_element = soup.find("strong", id="email")
    assert email_element is not None, "Email element with id 'email' not found!"
    try:
        validate_email(email_element.text)
    except EmailNotValidError as e:
        pytest.fail(f"The email link {email_element.text} is not valid: {e}")
    assert (
        email_element.text == user_email
    ), "Email content does not match the user's email!"

    link_element = soup.find("a", id="link")
    assert link_element is not None, "Reset link element with id 'link' not found!"
    reset_link = link_element["href"]
    assert validate_url(reset_link), f"The URL '{reset_link}' is not valid!"


@pytest.mark.e2e
@pytest.mark.order(5)
@pytest.mark.asyncio
async def test_reset_password(e2e_client, e2e_db_session, settings):
    user_email = "test@mate.com"
    new_password = "NewSecurePassword123!"

    stmt = (
        select(PasswordResetTokenModel)
        .join(UserModel)
        .where(UserModel.email == user_email)
    )
    result = await e2e_db_session.execute(stmt)
    reset_token_record = result.scalars().first()

    assert (
        reset_token_record
    ), f"Password reset token for email {user_email} was not found!"
    reset_token = reset_token_record.token

    reset_url = "/api/v1/accounts/reset-password/complete/"
    response = await e2e_client.post(
        reset_url,
        json={"email": user_email, "password": new_password, "token": reset_token},
    )

    assert (
        response.status_code == 200
    ), f"Expected status code 200, got {response.status_code}"
    response_data = response.json()
    assert (
        response_data["message"] == "Password reset successfully."
    ), "Unexpected password reset message!"

    stmt_deleted = select(PasswordResetTokenModel).where(
        PasswordResetTokenModel.user_id == reset_token_record.user_id
    )
    deleted_result = await e2e_db_session.execute(stmt_deleted)
    deleted_token = deleted_result.scalars().first()
    assert deleted_token is None, "Password reset token was not deleted after use!"

    stmt_user = select(UserModel).where(UserModel.email == user_email)
    user_result = await e2e_db_session.execute(stmt_user)
    updated_user = user_result.scalars().first()
    assert updated_user is not None, f"User with email {user_email} not found!"
    assert updated_user.verify_password(
        new_password
    ), "Password was not updated successfully!"

    await e2e_db_session.commit()

    mailhog_url = (
        f"http://{settings.EMAIL_HOST}:{settings.MAILHOG_API_PORT}/api/v2/messages"
    )
    async with httpx.AsyncClient() as client:
        mailhog_response = await client.get(mailhog_url)

    assert mailhog_response.status_code == 200, "Failed to fetch emails from MailHog!"
    messages = mailhog_response.json()["items"]
    assert len(messages) > 0, "No emails were sent!"

    email_data = messages[0]
    assert (
        email_data["Content"]["Headers"]["To"][0] == user_email
    ), "Recipient email does not match!"
    email_subject = email_data["Content"]["Headers"].get("Subject", [None])[0]
    assert (
        email_subject == "Your Password Has Been Successfully Reset"
    ), f"Expected subject 'Your Password Has Been Successfully Reset', but got '{email_subject}'"

    email_html = email_data["Content"]["Body"]
    soup = BeautifulSoup(email_html, "html.parser")

    email_element = soup.find("strong", id="email")
    assert email_element is not None, "Email element with id 'email' not found!"
    try:
        validate_email(email_element.text)
    except EmailNotValidError as e:
        pytest.fail(f"The email link {email_element.text} is not valid: {e}")
    assert (
        email_element.text == user_email
    ), "Email content does not match the user's email!"

    link_element = soup.find("a", id="link")
    assert link_element is not None, "Login link element with id 'link' not found!"
    login_url = link_element["href"]
    assert validate_url(login_url), f"The URL '{login_url}' is not valid!"


@pytest.mark.e2e
@pytest.mark.order(6)
@pytest.mark.asyncio
async def test_user_login_with_new_password(e2e_client, e2e_db_session):
    user_data = {"email": "test@mate.com", "password": "NewSecurePassword123!"}

    login_url = "/api/v1/accounts/login/"
    response = await e2e_client.post(login_url, json=user_data)
    assert (
        response.status_code == 201
    ), f"Expected status code 201, got {response.status_code}"

    response_data = response.json()
    assert "access_token" in response_data, "Access token is missing in response!"
    assert "refresh_token" in response_data, "Refresh token is missing in response!"

    refresh_token = response_data["refresh_token"]

    stmt = (
        select(RefreshTokenModel)
        .options(joinedload(RefreshTokenModel.user))
        .where(RefreshTokenModel.token == refresh_token)
    )
    result = await e2e_db_session.execute(stmt)
    stored_token = result.scalars().first()

    assert stored_token is not None, "Refresh token was not stored in the database!"
    assert (
        stored_token.user.email == user_data["email"]
    ), "Refresh token is linked to the wrong user!"
