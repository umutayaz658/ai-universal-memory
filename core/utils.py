from django.db import models
from cryptography.fernet import Fernet
from django.conf import settings
import base64

class EncryptedField(models.TextField):
    """
    A custom model field that encrypts data when saving to the DB 
    and decrypts when retrieving.
    Uses Fernet symmetric encryption.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fernet = self._get_fernet()

    def _get_fernet(self):
        # Derive a 32-byte URL-safe base64-encoded key from SECRET_KEY
        # This ensures the key is consistent but unique per project
        # In production, use a dedicated os.environ['ENCRYPTION_KEY']
        key_material = settings.SECRET_KEY.encode()[:32]
        # Pad if short (though Django default keys are usually long enough)
        key_material = key_material.ljust(32, b'0') 
        final_key = base64.urlsafe_b64encode(key_material)
        return Fernet(final_key)

    def get_prep_value(self, value):
        """Encrypts data before sending to the database API."""
        if value is None:
            return None
        
        # Ensure it's string before encrypting
        value_str = str(value)
        encrypted_value = self.fernet.encrypt(value_str.encode())
        return encrypted_value.decode('utf-8')  # Store as string in DB

    def from_db_value(self, value, expression, connection):
        """Decrypts data when loading from the database."""
        if value is None:
            return None

        try:
            # Attempt to decrypt
            decrypted_value = self.fernet.decrypt(value.encode()).decode()
            return decrypted_value
        except Exception:
            # Graceful Degradation:
            # If decryption fails (e.g., data was stored continuously before encryption),
            # return the raw value to avoid crashing the app.
            return value

    def to_python(self, value):
        """Standard method for deserialization, though from_db_value handles main logic."""
        if value is None:
            return None
        return value
