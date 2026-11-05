# Hospital Management System

A Python desktop application for hospital operations, built with OOP, custom
data structures, CustomTkinter, and SQLite.

## Run

Install the declared dependency and launch the application:

```powershell
python -m pip install -r requirements.txt
python main.py
```

The application initializes its SQLite database at
`data/hospital_management.db`. On a new installation, it prompts for the
single initial Owner account. Subsequent launches show the staff sign-in
screen. Passwords must contain at least 12 characters.

## Current interface

- English interface with support for Arabic usernames and text.
- First-run Owner setup, sign-in, session sign-out, and role-specific dashboards.
- Owner and Admin can create ordinary staff accounts; Owner cannot be created
  through account administration.
- Department administration: create, update, search, activate, and deactivate.
- Doctor directory: link an existing active Doctor account to an active
  department, update the directory, and activate or deactivate the entry.
- Patient demographics: register, search, update, activate, and deactivate
  patients without exposing clinical record contents.
- Appointment scheduling and administrative emergency intake are connected to
  their Services and SQLite history. Medical-record modules remain unavailable
  until their Service workflows and screens are implemented.
- UI controls are not an authorization boundary; Service-layer authorization
  validates protected operations.

## Architecture

The application follows UI → Services → Repositories → SQLite. Authentication,
authorization, directory workflows, password hashing, and account creation are
implemented in Services. Every directory write and its audit event share one
SQLite transaction. The UI does not access repositories or execute SQL.
