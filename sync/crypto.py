from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class DeviceKeyPair:
    private_key_b64: str
    public_key_b64: str


def generate_device_keypair() -> DeviceKeyPair:
    sk = x25519.X25519PrivateKey.generate()
    pk = sk.public_key()
    return DeviceKeyPair(
        private_key_b64=_b64e(
            sk.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        ),
        public_key_b64=_b64e(pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)),
    )


def generate_group_key() -> bytes:
    return os.urandom(32)


def _derive_wrap_key(shared_secret: bytes, context: bytes = b"diary-sync-wrap-v1") -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=context,
    )
    return hkdf.derive(shared_secret)


def seal_group_key_for_device(*, group_key: bytes, device_public_key_b64: str) -> Dict[str, str]:
    eph_sk = x25519.X25519PrivateKey.generate()
    eph_pk = eph_sk.public_key()
    dev_pk = x25519.X25519PublicKey.from_public_bytes(_b64d(device_public_key_b64))
    shared = eph_sk.exchange(dev_pk)
    wrap_key = _derive_wrap_key(shared)

    nonce = os.urandom(12)
    aad = b"diary-sync-group-key"
    ct = AESGCM(wrap_key).encrypt(nonce, group_key, aad)
    return {
        "ephemeral_pub": _b64e(eph_pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)),
        "nonce": _b64e(nonce),
        "ciphertext": _b64e(ct),
    }


def open_group_key_for_device(*, envelope: Dict[str, str], device_private_key_b64: str) -> bytes:
    sk = x25519.X25519PrivateKey.from_private_bytes(_b64d(device_private_key_b64))
    eph_pk = x25519.X25519PublicKey.from_public_bytes(_b64d(str(envelope["ephemeral_pub"])))
    shared = sk.exchange(eph_pk)
    wrap_key = _derive_wrap_key(shared)
    nonce = _b64d(str(envelope["nonce"]))
    ct = _b64d(str(envelope["ciphertext"]))
    return AESGCM(wrap_key).decrypt(nonce, ct, b"diary-sync-group-key")


def encrypt_json(*, key: bytes, payload: Dict[str, Any], aad: Dict[str, Any] | None = None) -> Dict[str, str]:
    nonce = os.urandom(12)
    aad_bytes = _canon(aad or {})
    pt = _canon(payload)
    ct = AESGCM(key).encrypt(nonce, pt, aad_bytes)
    return {"nonce": _b64e(nonce), "ciphertext": _b64e(ct)}


def decrypt_json(*, key: bytes, box: Dict[str, str], aad: Dict[str, Any] | None = None) -> Dict[str, Any]:
    nonce = _b64d(str(box["nonce"]))
    ct = _b64d(str(box["ciphertext"]))
    aad_bytes = _canon(aad or {})
    pt = AESGCM(key).decrypt(nonce, ct, aad_bytes)
    return json.loads(pt.decode("utf-8"))


def event_digest_hex(event_obj: Dict[str, Any]) -> str:
    return sha256(_canon(event_obj)).hexdigest()
