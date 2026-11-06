"""Optional Microsoft Entra ID adapter."""

import msal


class EntraAuth:
    def __init__(self, settings):
        self.settings = settings
        if settings.identity_mode != "entra":
            raise RuntimeError("EntraAuth requires IDENTITY_MODE=entra")
        missing = settings.validate_for_runtime()
        if missing:
            raise RuntimeError("; ".join(missing))
        self.authority = f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        self.client = msal.ConfidentialClientApplication(
            settings.entra_client_id,
            authority=self.authority,
            client_credential=settings.entra_client_secret,
        )

    def login_url(self, state: str) -> str:
        return self.client.get_authorization_request_url(
            ["openid", "profile", "email"],
            state=state,
            redirect_uri=self.settings.entra_redirect_uri,
        )

    def redeem(self, auth_response: dict) -> dict:
        result = self.client.acquire_token_by_authorization_code(
            auth_response.get("code", ""),
            scopes=["openid", "profile", "email"],
            redirect_uri=self.settings.entra_redirect_uri,
        )
        if "id_token_claims" not in result:
            raise PermissionError("Entra authorization failed")
        return result["id_token_claims"]
