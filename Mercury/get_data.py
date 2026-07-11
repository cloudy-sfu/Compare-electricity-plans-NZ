import base64
import hashlib
import json
import re
import secrets
import chompjs
import uuid
from urllib.parse import parse_qs, urlparse
import pandas as pd
from requests import Session

with open("Mercury/header_usage.json") as f:
    header_usage = json.load(f)
with open("Mercury/header_main_js.json") as f:
    header_main_js = json.load(f)
with open("Mercury/header_authorize.json") as f:
    header_authorize = json.load(f)
with open("Mercury/header_self_asserted.json") as f:
    header_self_asserted = json.load(f)
with open("Mercury/header_confirmed.json") as f:
    header_confirmed = json.load(f)


def pkce_pair():
    """
    :return: verifier & challenge pair for PKCE (S256).
    """
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def decode_jwt_payload(jwt_payload):
    payload = jwt_payload.split(".")[1]
    payload += "=" * (-len(payload) % 4)  # restore base64 padding
    return json.loads(base64.urlsafe_b64decode(payload).decode())


def login(username, password):
    # Get main-XEUMSWUY.js
    sess_1 = Session()
    sess_1.trust_env = False
    main_js_response = sess_1.get(
        "https://myaccount.mercury.co.nz/main-XEUMSWUY.js",
        headers=header_main_js
    )
    main_js = main_js_response.text
    bt = re.search(r"var\s*Bt\s*=\s*({.*?})\s*;", main_js)
    if not bt:
        raise Exception("Cannot parse MSAL fields from "
                        "https://myaccount.mercury.co.nz/main-XEUMSWUY.js")
    bt = bt.group(1)
    bt = chompjs.parse_js_object(bt)

    # Authorize
    verifier_1, challenge_1 = pkce_pair()
    state_1 = base64.b64encode(bytes(
        json.dumps(
            {"id": str(uuid.uuid4()), "meta": {"interactionType": "redirect"}},
            separators=(",", ":")
        )
        , "utf-8")
    )
    nonce_1 = str(uuid.uuid4())
    authorize_1_response = sess_1.get(
        f"{bt['msalAuthority']}/b2c_1a_signup_signin/oauth2/v2.0/authorize",
        headers=header_authorize,
        params={
            "client_id": bt["msalClientId"],
            "scope": f"{bt["msalScopesUrl"]}/customer:write "
                     f"{bt["msalScopesUrl"]}/customer:read openid profile offline_access",
            "redirect_uri": "https://myaccount.mercury.co.nz",
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": challenge_1,
            "state": state_1,
            "nonce": nonce_1,
        }
    )
    authorize_1 = authorize_1_response.text
    settings = re.search(r"var\s*SETTINGS\s*=\s*({.*?})\s*;", authorize_1)
    if not settings:
        raise Exception(f"Cannot parse settings fields from {bt['msalAuthority']}/"
                        f"b2c_1a_signup_signin/oauth2/v2.0/authorize")
    settings = settings.group(1)
    settings = chompjs.parse_js_object(settings)

    header_self_asserted_1 = header_self_asserted.copy()
    header_self_asserted_1["x-csrf-token"] = settings["csrf"]
    header_self_asserted_1["referer"] = authorize_1_response.url
    credential_feedback = sess_1.post(
        f"{bt['msalAuthority']}/{settings["hosts"]["policy"].lower()}/SelfAsserted",
        headers=header_self_asserted_1,
        params={
            "tx": settings["transId"],
            "p": settings["hosts"]["policy"],
        },
        data={
            "request_type": "RESPONSE",
            "signInName": username,
            "password": password,
        }
    )
    credential_feedback.raise_for_status()
    assert credential_feedback.json().get("status") == "200", \
        "Login Mercury not successful."

    # Confirm authentication
    header_confirmed_1 = header_confirmed.copy()
    header_confirmed_1["referer"] = authorize_1_response.url
    now_unix_timestamp = int(pd.Timestamp('now', tz="UTC").timestamp())
    confirmed_response = sess_1.get(
        f"{bt['msalAuthority']}/{settings["hosts"]["policy"]}/api/CombinedSigninAndSignup/confirmed",
        headers=header_confirmed_1,
        params={
            "rememberMe": "false",
            "csrf_token": settings["csrf"],
            "tx": settings["transId"],
            "p": settings["hosts"]["policy"],
            "diags": {
                "pageViewId": settings["pageViewId"],
                "pageId": "CombinedSigninAndSignup",
                "trace": [
                    {"ac":"T005", "acST": now_unix_timestamp, "acD": 1},
                    {"ac":"T021 - URL:https://cdn.mercury.co.nz/b2c/login/index.html",
                     "acST": now_unix_timestamp, "acD": 14},
                    {"ac":"T019", "acST": now_unix_timestamp, "acD": 2},
                    {"ac": "T004", "acST": now_unix_timestamp, "acD": 1},
                    {"ac": "T003", "acST": now_unix_timestamp, "acD": 1},
                    {"ac": "T035", "acST": now_unix_timestamp, "acD": 0},
                    {"ac": "T030Online", "acST": 1783748488, "acD": 0},
                    {"ac": "T002", "acST": now_unix_timestamp + 18, "acD": 0},
                    {"ac": "T018T010", "acST": now_unix_timestamp + 17, "acD": 530}
                ]
            }
        },
        allow_redirects=False
    )
    next_location = confirmed_response.headers.get("Location")
    auth_code = parse_qs(urlparse(next_location).query)["code"][0]

    # From authentication code to tokens
    token_client_request_id = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    msal_uuid = re.search(r"/(.*?)/", settings["hosts"]["tenant"]).group(1)
    token_response = sess_1.post(
        f"{bt['msalAuthority']}/{settings["hosts"]["policy"].lower()}/oauth2/v2.0/token",
        headers=header_usage,
        data={
            "client_id": bt["msalClientId"],
            "redirect_uri": "https://myaccount.mercury.co.nz",
            "scope": f"{bt["msalScopesUrl"]}/customer:write "
                     f"{bt["msalScopesUrl"]}/customer:read openid profile offline_access",
            "code": auth_code,
            "x-client-SKU": "msal.js.browser",
            "x-client-VER": "3.0.2",
            "x-ms-lib-capability": "retry-after, h429",
            "x-client-current-telemetry": "5|865,0,,,|@azure/msal-angular,3.0.2",
            "x-client-last-telemetry": "5|0|||0,0",
            "code_verifier": verifier_1,
            "grant_type": "authorization_code",
            "client_info": "1",
            "client-request-id": token_client_request_id,
            "X-AnchorMailbox": f"Oid:{oid}-{settings["hosts"]["policy"].lower()}@{msal_uuid}",
        }
    )
    token = token_response.json()

    # ocp-apim-subscription-key
    token[bt["apiHeaderKey"]] = bt["apiHeaderValue"]
    return token


def get_customer_id(access_token):
    customer_info = decode_jwt_payload(access_token)
    return customer_info["extension_customerId"]


def get_accounts(access_token, ocp_key, customer_id):
    sess_2 = Session()
    sess_2.trust_env = False
    header_usage_1 = header_usage.copy()
    header_usage_1["authorization"] = f"Bearer {access_token}"
    header_usage_1["ocp-apim-subscription-key"] = ocp_key

    accounts_response = sess_2.get(
        f"https://apis.mercury.co.nz/selfservice/v1/customers/{customer_id}/accounts",
        headers=header_usage_1,
    )
    accounts = accounts_response.json()
    return accounts


def get_electricity_services(access_token, ocp_key, customer_id, account_id):
    sess_2 = Session()
    sess_2.trust_env = False
    header_usage_1 = header_usage.copy()
    header_usage_1["authorization"] = f"Bearer {access_token}"
    header_usage_1["ocp-apim-subscription-key"] = ocp_key

    services_response = sess_2.get(
        f"https://apis.mercury.co.nz/selfservice/v1/customers/{customer_id}/"
        f"accounts/{account_id}/services",
        headers=header_usage_1,
        params={"includeAll": "false"},
    )
    electricity_services = [
        x for x in services_response.json()['services']
        if x["serviceGroup"] == "Electricity"
    ]
    return electricity_services


def get_usage(access_token, ocp_key, customer_id, account_id, service_id,
              start_time, end_time):
    start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S%z")
    start_time_str = start_time_str[:-2] + ":" + start_time_str[-2:]
    end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%S%z")
    end_time_str = end_time_str[:-2] + ":" + end_time_str[-2:]

    sess_2 = Session()
    sess_2.trust_env = False
    header_usage_1 = header_usage.copy()
    header_usage_1["authorization"] = f"Bearer {access_token}"
    header_usage_1["ocp-apim-subscription-key"] = ocp_key

    usage_response = sess_2.get(
        f"https://apis.mercury.co.nz/selfservice/v1/customers/{customer_id}/"
        f"accounts/{account_id}/services/electricity/{service_id}/usage",
        headers=header_usage_1,
        params={
            "interval": "hourly",
            "startDate": start_time_str,
            "endDate": end_time_str
        }
    )
    usage_wrappers = usage_response.json()["usage"]
    usages = []
    for usage_wrapper in usage_wrappers:
        usage = usage_wrapper["data"]
        usage = pd.DataFrame(usage)
        usage = usage[["date", "consumption"]]
        usage.set_index("date", inplace=True)
        usages.append(usage)
    usages = pd.concat(usages, axis=1).sum(axis=1)
    return usages
