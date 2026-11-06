"""Optional Microsoft Entra ID adapter using MSAL's web auth-code flow."""

import msal


class EntraAuth:
    def __init__(self, settings, http_client=None):
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
            http_client=http_client,
        )

    def begin(self, state: str) -> dict:
        """Create MSAL's state/nonce/PKCE-bound authorization-code flow."""
        flow = self.client.initiate_auth_code_flow(
            scopes=[],
            state=state,
            redirect_uri=self.settings.entra_redirect_uri,
            response_mode="form_post",
        )
        if "error" in flow:
            raise PermissionError("Entra authorization could not be started")
        return flow

    def redeem(self, flow: dict, auth_response: dict) -> dict:
        """Redeem the exact flow so MSAL validates state, nonce, and PKCE."""
        result = self.client.acquire_token_by_auth_code_flow(
            flow,
            auth_response,
        )
        if "error" in result or not isinstance(result.get("id_token_claims"), dict):
            raise PermissionError("Entra authorization failed")
        return result["id_token_claims"]
