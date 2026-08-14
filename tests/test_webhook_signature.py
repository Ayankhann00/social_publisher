from common.security import sign_payload, verify_signature

SECRET = "test-secret"


def test_valid_signature_is_accepted():
    payload = {"post_id": "abc", "result": "published"}
    signature = sign_payload(payload, SECRET)
    assert verify_signature(payload, signature, SECRET) is True


def test_forged_signature_is_rejected():
    payload = {"post_id": "abc", "result": "published"}
    real_signature = sign_payload(payload, SECRET)

    tampered_payload = {"post_id": "abc", "result": "failed"}
    assert verify_signature(tampered_payload, real_signature, SECRET) is False


def test_wrong_secret_is_rejected():
    payload = {"post_id": "abc", "result": "published"}
    signature = sign_payload(payload, "some-other-secret")
    assert verify_signature(payload, signature, SECRET) is False
