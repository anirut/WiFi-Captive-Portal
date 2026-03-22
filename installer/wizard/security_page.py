"""Security configuration page."""

import secrets
from PyQt6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QGroupBox,
    QGridLayout,
    QCheckBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..utils.validators import validate_username, validate_password


class SecurityPage(QWizardPage):
    """Page for security configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Security Configuration")
        self.setSubTitle("Set up admin credentials and security keys")

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Admin credentials group
        admin_group = QGroupBox("Admin Credentials")
        admin_layout = QGridLayout(admin_group)

        # Username
        admin_layout.addWidget(QLabel("Admin Username:"), 0, 0)
        self.username_edit = QLineEdit("admin")
        self.username_edit.setPlaceholderText("Admin username")
        admin_layout.addWidget(self.username_edit, 0, 1)

        # Password
        admin_layout.addWidget(QLabel("Admin Password:"), 1, 0)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Enter password (min 8 characters)")
        admin_layout.addWidget(self.password_edit, 1, 1)

        # Show password checkbox
        self.show_password_cb = QCheckBox("Show password")
        self.show_password_cb.toggled.connect(
            lambda checked: self.password_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        admin_layout.addWidget(self.show_password_cb, 1, 2)

        # Confirm password
        admin_layout.addWidget(QLabel("Confirm Password:"), 2, 0)
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_edit.setPlaceholderText("Confirm password")
        admin_layout.addWidget(self.confirm_password_edit, 2, 1)

        # Generate password button
        gen_pwd_btn = QPushButton("Generate")
        gen_pwd_btn.clicked.connect(self._generate_password)
        admin_layout.addWidget(gen_pwd_btn, 2, 2)

        layout.addWidget(admin_group)

        # Security keys group
        keys_group = QGroupBox("Security Keys")
        keys_layout = QGridLayout(keys_group)

        # Secret Key
        keys_layout.addWidget(QLabel("JWT Secret Key:"), 0, 0)
        self.secret_key_edit = QLineEdit()
        self.secret_key_edit.setPlaceholderText("Auto-generated")
        self.secret_key_edit.setReadOnly(True)
        keys_layout.addWidget(self.secret_key_edit, 0, 1)

        gen_secret_btn = QPushButton("Generate")
        gen_secret_btn.clicked.connect(self._generate_secret_key)
        keys_layout.addWidget(gen_secret_btn, 0, 2)

        # Encryption Key
        keys_layout.addWidget(QLabel("Encryption Key:"), 1, 0)
        self.encryption_key_edit = QLineEdit()
        self.encryption_key_edit.setPlaceholderText("Auto-generated")
        self.encryption_key_edit.setReadOnly(True)
        keys_layout.addWidget(self.encryption_key_edit, 1, 1)

        gen_enc_btn = QPushButton("Generate")
        gen_enc_btn.clicked.connect(self._generate_encryption_key)
        keys_layout.addWidget(gen_enc_btn, 1, 2)

        # Auto-generate checkbox
        self.auto_generate_cb = QCheckBox("Auto-generate all keys")
        self.auto_generate_cb.setChecked(True)
        keys_layout.addWidget(self.auto_generate_cb, 2, 0, 1, 3)

        layout.addWidget(keys_group)

        # Session settings group
        session_group = QGroupBox("Session Settings")
        session_layout = QGridLayout(session_group)

        # JWT expiration
        session_layout.addWidget(QLabel("Session Duration:"), 0, 0)
        self.jwt_expire_edit = QLineEdit("24")
        self.jwt_expire_edit.setPlaceholderText("Hours")
        self.jwt_expire_edit.setMaximumWidth(100)
        session_layout.addWidget(self.jwt_expire_edit, 0, 1)

        hours_label = QLabel("hours")
        session_layout.addWidget(hours_label, 0, 2)

        # Rate limit
        session_layout.addWidget(QLabel("Auth Rate Limit:"), 1, 0)
        self.rate_limit_edit = QLineEdit("5")
        self.rate_limit_edit.setPlaceholderText("Attempts")
        self.rate_limit_edit.setMaximumWidth(100)
        session_layout.addWidget(self.rate_limit_edit, 1, 1)

        rate_label = QLabel("attempts per minute")
        session_layout.addWidget(rate_label, 1, 2)

        layout.addWidget(session_group)

        # Validation status
        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("padding: 5px;")
        layout.addWidget(self.validation_label)

        # Connect validators
        self.username_edit.textChanged.connect(self._validate)
        self.password_edit.textChanged.connect(self._validate)
        self.confirm_password_edit.textChanged.connect(self._validate)

        layout.addStretch()

        # Register fields
        self.registerField("admin_username", self.username_edit)
        self.registerField("admin_password", self.password_edit)
        self.registerField("secret_key", self.secret_key_edit)
        self.registerField("encryption_key", self.encryption_key_edit)
        self.registerField("jwt_expire_hours", self.jwt_expire_edit)
        self.registerField("auth_rate_limit", self.rate_limit_edit)

        # Auto-generate keys on first show
        self._initialized = False

    def initializePage(self):
        """Called when page is shown."""
        if not self._initialized:
            self._generate_secret_key()
            self._generate_encryption_key()
            self._initialized = True

    def _generate_password(self):
        """Generate a random password."""
        password = secrets.token_urlsafe(16)
        self.password_edit.setText(password)
        self.confirm_password_edit.setText(password)

    def _generate_secret_key(self):
        """Generate JWT secret key."""
        self.secret_key_edit.setText(secrets.token_hex(32))

    def _generate_encryption_key(self):
        """Generate Fernet encryption key."""
        from cryptography.fernet import Fernet
        self.encryption_key_edit.setText(Fernet.generate_key().decode())

    def _validate(self):
        """Validate security configuration."""
        errors = []

        # Validate username
        ok, msg = validate_username(self.username_edit.text())
        if not ok:
            errors.append(f"Username: {msg}")

        # Validate password
        ok, msg = validate_password(self.password_edit.text())
        if not ok:
            errors.append(f"Password: {msg}")

        # Check password match
        if self.password_edit.text() != self.confirm_password_edit.text():
            errors.append("Passwords do not match")

        if errors:
            self.validation_label.setText("❌ " + "\n".join(errors))
            self.validation_label.setStyleSheet("color: red; padding: 5px;")
        else:
            self.validation_label.setText("✅ Configuration valid")
            self.validation_label.setStyleSheet("color: green; padding: 5px;")

        self.completeChanged.emit()

    def isComplete(self):
        """Check if page is complete."""
        ok, _ = validate_username(self.username_edit.text())
        if not ok:
            return False

        ok, _ = validate_password(self.password_edit.text())
        if not ok:
            return False

        if self.password_edit.text() != self.confirm_password_edit.text():
            return False

        return True

    def get_config(self):
        """Get security configuration."""
        return {
            "admin_username": self.username_edit.text(),
            "admin_password": self.password_edit.text(),
            "secret_key": self.secret_key_edit.text(),
            "encryption_key": self.encryption_key_edit.text(),
            "jwt_expire_hours": int(self.jwt_expire_edit.text() or "24"),
            "auth_rate_limit": int(self.rate_limit_edit.text() or "5"),
        }
