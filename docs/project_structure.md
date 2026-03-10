# Project Structure

This project uses a simplified Django layout for local prototype work.

## Core layout

- `apps/`
  - `api/` API models, serializers, viewsets, admin, commands
  - `user_app/` user-facing views and logic
  - `admin_app/` custom admin site/dashboard
- `nutrigem_backend/`
  - `settings_base.py` shared settings
  - `settings_local.py` local/dev overrides
  - `settings.py` local settings entrypoint
  - `urls.py`, `asgi.py`, `wsgi.py`
- `templates/` global Django templates
- `static/` source static assets
- `staticfiles/` collected static output
- `docs/` project docs and conventions
## Environment strategy

- `settings.py` always loads `settings_local.py`
- MySQL env vars (`DB_*`) are the expected local configuration

## Why this is better

- Less deployment-specific setup for a prototype.
- Fewer config branches to debug.
- Onboarding stays focused on local development.
