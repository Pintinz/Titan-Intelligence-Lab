import os

# The offline/bcrypt auth path (`/auth/register`, `/auth/login`) defaults OFF in production
# (Security Milestone finding H-4 — see apps/api/routers/identity_router.py's
# `_offline_auth_enabled`). The test suite is exactly the "tests" half of that flag's own stated
# "on only for tests/local dev" carve-out, so it's set here once for the whole run rather than in
# every one of the ~40 test files that call these endpoints.
os.environ.setdefault("TITANIQ_ENABLE_OFFLINE_AUTH", "true")
