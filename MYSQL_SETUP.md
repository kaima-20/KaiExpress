# KaiExpress MySQL Setup

The active application is `setup.py` plus the `packages` package. It uses MySQL when `DATABASE_URL` or `MYSQL_HOST` is configured, and SQLite only when neither is present.

## 1. Create the database

Run this in MySQL as an administrator:

```sql
CREATE DATABASE kaiexpress CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kaiexpress_user'@'localhost' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT ALL PRIVILEGES ON kaiexpress.* TO 'kaiexpress_user'@'localhost';
FLUSH PRIVILEGES;
```

## 2. Configure the application

Copy `.env.example` to `.env` and set the real password:

```env
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=mysql+pymysql://kaiexpress_user:replace-with-a-strong-password@127.0.0.1:3306/kaiexpress
```

The app also accepts the separate `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD` variables.

## 3. Install dependencies and start

Use the workspace virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python setup.py
```

On startup, SQLAlchemy creates the application tables and seeds the demo catalog if it is not already present.

## Payout behavior

Restaurant payouts are stored in the MySQL `payouts` table. The app calculates:

- Gross order revenue
- A 10% platform fee
- Available restaurant balance
- Payout request amount and status
- A unique payout reference

The current implementation records payout requests in the database. Sending money to a bank or mobile-money wallet still requires a provider such as Stripe Connect, Paystack, or Flutterwave and provider credentials.
