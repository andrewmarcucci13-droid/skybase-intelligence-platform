"""Application configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

# Stripe
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID: str = os.getenv("STRIPE_PRICE_ID", "price_1TNhCiB6nlyxBcZvphYPYmK5")
STRIPE_SUB_PRICE_ID: str = os.getenv("STRIPE_SUB_PRICE_ID", "price_1TNhCiB6nlyxBcZvchN2Q9CA")

# App
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://skybaseintel.com")
APP_ENV: str = os.getenv("APP_ENV", "development")
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
