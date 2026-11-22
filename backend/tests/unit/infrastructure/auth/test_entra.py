"""The Entra provider: what it accepts as a verified ID token, and what it makes of the claims."""

import json
import time
from typing import Any

import httpx
import jwt
import pytest
from crudauth.oauth import OAuthUserInfo
from cryptography.hazmat.primitives.asymmetric import rsa

from src.infrastructure.auth.entra import EntraIDProvider, EntraTokenError, app_roles_of, groups_of

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks() -> dict[str, Any]:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
    return {"keys": [{**public, "kid": "k1", "use": "sig", "kty": "RSA"}]}


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": CLIENT,
        "tid": TENANT,
        "oid": "99999999-8888-7777-6666-555555555555",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "name": "Avery Inspector",
        "preferred_username": "Avery.Inspector@example.com",
        "roles": ["QC.Admin"],
        "groups": ["AABBCCDD-0000-0000-0000-000000000001"],
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _token(key: Any = _KEY, kid: str = "k1", **overrides: Any) -> str:
    return jwt.encode(_claims(**overrides), key, algorithm="RS256", headers={"kid": kid})


def _provider(id_token: str | None = None) -> EntraIDProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/discovery/v2.0/keys"):
            return httpx.Response(200, json=_jwks())
        if request.url.path.endswith("/oauth2/v2.0/token"):
            body = {"access_token": "at-1", "token_type": "Bearer"}
            if id_token:
                body["id_token"] = id_token
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    cls = EntraIDProvider.for_tenant(TENANT)
    return cls(CLIENT, "secret", "http://localhost/cb", transport=httpx.MockTransport(handler))


async def test_a_valid_token_flows_through_the_callback_steps():
    provider = _provider(_token())
    await provider.initialize()

    token = await provider.exchange_code("code", code_verifier="v")
    raw = await provider.get_user_info(token["access_token"])
    info = await provider.process_user_info(raw)

    assert info.provider == "entra"
    assert info.provider_user_id == "99999999-8888-7777-6666-555555555555"
    assert info.email == "avery.inspector@example.com"
    assert info.email_verified is True
    assert info.username == "Avery.Inspector"
    assert app_roles_of(info) == ["QC.Admin"]
    assert groups_of(info) == ["aabbccdd-0000-0000-0000-000000000001"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"tid": "00000000-0000-0000-0000-000000000000"},
        {"iss": "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0"},
        {"aud": "someone-elses-app"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200, "nbf": int(time.time()) - 7200},
        {"oid": None},
    ],
    ids=["other-tenant", "other-issuer", "other-audience", "expired", "no-oid"],
)
async def test_a_token_that_fails_a_check_is_refused(overrides: dict[str, Any]):
    provider = _provider()
    await provider.initialize()

    with pytest.raises(EntraTokenError):
        await provider.verify_id_token(_token(**overrides))


async def test_a_token_signed_by_another_key_is_refused():
    provider = _provider()
    await provider.initialize()

    with pytest.raises(EntraTokenError):
        await provider.verify_id_token(_token(key=_OTHER_KEY))


async def test_an_unsigned_token_is_refused():
    provider = _provider()
    await provider.initialize()
    unsigned = jwt.encode(_claims(), key=None, algorithm="none")

    with pytest.raises(EntraTokenError):
        await provider.verify_id_token(unsigned)


async def test_no_id_token_means_no_sign_in():
    provider = _provider(id_token=None)
    await provider.initialize()

    with pytest.raises(EntraTokenError):
        await provider.exchange_code("code")


async def test_user_info_is_only_handed_out_for_the_token_just_verified():
    provider = _provider(_token())
    await provider.initialize()
    await provider.exchange_code("code")

    with pytest.raises(EntraTokenError):
        await provider.get_user_info("a-different-access-token")


async def test_user_info_is_not_handed_out_twice():
    provider = _provider(_token())
    await provider.initialize()
    token = await provider.exchange_code("code")
    await provider.get_user_info(token["access_token"])

    with pytest.raises(EntraTokenError):
        await provider.get_user_info(token["access_token"])


def test_a_provider_needs_a_tenant():
    with pytest.raises(ValueError):
        EntraIDProvider(CLIENT, "secret", "http://localhost/cb")


def test_groups_overage_reads_as_unknown_not_empty():
    info = OAuthUserInfo(
        provider="entra",
        provider_user_id="x",
        raw_data={"_claim_names": {"groups": "src1"}, "_claim_sources": {"src1": {}}},
    )

    assert groups_of(info) is None


def test_other_providers_have_no_entra_claims():
    info = OAuthUserInfo(provider="google", provider_user_id="x", raw_data={"roles": ["QC.Admin"]})

    assert app_roles_of(info) is None
    assert groups_of(info) is None
