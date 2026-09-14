import os
import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

# Initialize Firebase Admin SDK
# In production, this uses GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_CONFIG env vars.
# If those aren't present and we're not in test mode, it might fail. We'll catch and log.
try:
    if not firebase_admin._apps:
        # If FIREBASE_SERVICE_ACCOUNT_JSON is provided, use it. Otherwise, default credentials.
        cert_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        if cert_path and os.path.exists(cert_path):
            cred = credentials.Certificate(cert_path)
            firebase_admin.initialize_app(cred)
        else:
            # For token verification only, we just need the project ID
            firebase_admin.initialize_app(options={'projectId': 'gen-lang-client-0574518291'})
except Exception as e:
    print(f"Warning: Firebase Admin SDK initialization failed: {e}")

EXPECTED_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "gen-lang-client-0574518291")
ALLOWED_CLINICAL_ROLES = {"admin", "super_admin", "clinician"}

# Endpoints that bypass-mode tokens are NEVER permitted to call.
# Dispatch is the only endpoint that results in a live phone call to a real patient.
_BYPASS_BLOCKED_PATH_SUFFIXES = ("/dispatch",)


def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Verifies a Firebase ID token and validates origin audience/issuer.

    MEDOPS_BYPASS_AUTH / MEDOPS_TEST_MODE skip Firebase verification for local
    development and automated tests only.  Bypass-mode payloads carry
    _bypass_mode=True so downstream guards can block live-call endpoints.
    Never set these variables in production or staging environments.
    """
    bypass_auth = os.environ.get("MEDOPS_BYPASS_AUTH", "").lower() in ("1", "true", "yes", "on")
    test_mode = os.environ.get("MEDOPS_TEST_MODE", "").lower() in ("1", "true", "yes", "on")
    if bypass_auth or test_mode:
        token = credentials.credentials
        if "unauthorized" in token or "forbidden" in token:
            role = "unauthorized_guest"
        elif "admin" in token:
            role = "admin"
        else:
            role = "clinician"
        return {
            "uid": "test_user_id",
            "email": "test@medops.local",
            "role": role,
            "_bypass_mode": True,
        }

    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        aud = decoded_token.get("aud")
        iss = decoded_token.get("iss")
        expected_iss = f"https://securetoken.google.com/{EXPECTED_PROJECT_ID}"
        if aud != EXPECTED_PROJECT_ID or iss != expected_iss:
            raise HTTPException(
                status_code=401,
                detail=f"Arbitrary credential origin rejected: expected project {EXPECTED_PROJECT_ID}"
            )
        return decoded_token
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")


def verify_clinical_admin_role(
    request: Request,
    payload: dict = Security(verify_jwt_token),
) -> dict:
    """
    Enforces bounded role authorization for sensitive clinical actions.

    Rules:
    - The token must carry an explicit role claim; missing role is rejected.
    - The role must be in ALLOWED_CLINICAL_ROLES.
    - Bypass-mode tokens (_bypass_mode=True) are never permitted to call
      dispatch endpoints to prevent accidental live calls during development.
    """
    # --- Role presence check ---
    role = payload.get("role") or payload.get("custom_claims", {}).get("role")
    if not role:
        raise HTTPException(
            status_code=403,
            detail="Token carries no clinical role claim. "
                   "Ensure the Firebase custom claim 'role' is set for this user.",
        )

    # --- Role allowlist check ---
    if role not in ALLOWED_CLINICAL_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' is not authorized for sensitive clinical actions",
        )

    # --- Bypass-mode cannot reach live-call endpoints ---
    if payload.get("_bypass_mode"):
        path = request.url.path
        if any(path.endswith(suffix) for suffix in _BYPASS_BLOCKED_PATH_SUFFIXES):
            raise HTTPException(
                status_code=403,
                detail=(
                    "MEDOPS_BYPASS_AUTH / MEDOPS_TEST_MODE is active. "
                    "Dispatch to live provider is blocked in bypass mode to prevent "
                    "accidental calls to real patients. Disable bypass mode and use "
                    "real credentials to dispatch."
                ),
            )

    return payload
