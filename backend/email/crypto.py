import base64
import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger("crypto")

# Internal fallback key if ENCRYPTION_KEY environment variable is not defined.
# In production, ENCRYPTION_KEY must be a stable 32-byte key base64-encoded.
_fallback_key = Fernet.generate_key()
_fernet_instance = None

def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    
    key_str = os.getenv("ENCRYPTION_KEY")
    if not key_str:
        logger.warning(
            "ENCRYPTION_KEY environment variable is not set! Using temporary fallback key. "
            "Encrypted data (like OAuth refresh tokens) will NOT persist across backend restarts!"
        )
        _fernet_instance = Fernet(_fallback_key)
        return _fernet_instance
    
    try:
        # Check if it needs padding or is already valid base64 urlsafe
        key_bytes = key_str.encode("utf-8")
        _fernet_instance = Fernet(key_bytes)
        return _fernet_instance
    except Exception as e:
        logger.error(f"Failed to initialize Fernet with ENCRYPTION_KEY: {e}. Falling back to temporary key.")
        _fernet_instance = Fernet(_fallback_key)
        return _fernet_instance

def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token string and return a base64 encoded ciphertext string."""
    if not token:
        return ""
    fernet = get_fernet()
    token_bytes = token.encode("utf-8")
    encrypted_bytes = fernet.encrypt(token_bytes)
    return encrypted_bytes.decode("utf-8")

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a base64 encoded ciphertext string and return the plaintext token."""
    if not encrypted_token:
        return ""
    fernet = get_fernet()
    try:
        encrypted_bytes = encrypted_token.encode("utf-8")
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to decrypt token: {e}")
        raise ValueError("Decryption failed. Token might be corrupted or the encryption key changed.")
