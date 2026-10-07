"""Signature contract tests.

Golden values come from the official BitUnix doc example
(https://openapidoc.bitunix.com/api-docs/futures/common/sign.html).

The signature is the money/security path: if it drifts, every private
call fails, so we pin it against the published example.
"""

from src.client import sha256_hex, sign

# Official doc example — do not change.
NONCE = "123456"
TIMESTAMP = "20241120123045"
API_KEY = "yourApiKey"
SECRET_KEY = "yourSecretKey"
QUERY = "id1uid200"
BODY = '{"uid":"2899","arr":[{"id":1,"name":"maple"},{"id":2,"name":"lily"}]}'

GOLDEN_DIGEST = "75099831ac6803e9c5b79dd3cde2c3c529b4750bd3508186afdde0dd13599b38"
GOLDEN_SIGN = "00397cd1e52c7dce3258067324363b6361fabc9178a0912b330c138db8745655"


def test_sha256_hex_matches_known_value():
    assert sha256_hex("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sign_matches_official_example():
    digest = sha256_hex(NONCE + TIMESTAMP + API_KEY + QUERY + BODY)
    assert digest == GOLDEN_DIGEST, "digest step deviates from official example"
    assert sign(SECRET_KEY, NONCE, TIMESTAMP, API_KEY, QUERY, BODY) == GOLDEN_SIGN


if __name__ == "__main__":
    test_sha256_hex_matches_known_value()
    test_sign_matches_official_example()
    print("ok: signature golden values match")
