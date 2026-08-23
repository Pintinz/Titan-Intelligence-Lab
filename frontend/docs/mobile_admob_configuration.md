# Mobile AdMob Configuration — Required External Setup

Real, buildable code for the AdMob rewarded-prediction unlock (see
`docs/mobile_architecture_audit.md` for the Capacitor mobile app this extends) ships in this
repository. As of 2026-08-23, the user's real AdMob account is configured — everything below
reflects the actual live state, not a hypothetical.

## Done — real AdMob resources, created live in the user's account

| | Android | iOS |
|---|---|---|
| App ID | `ca-app-pub-5093738800594754~9488584536` | `ca-app-pub-5093738800594754~5263128013` |
| Rewarded ad unit ("Prediction Unlock", reward amount 2, item "predictions") | `ca-app-pub-5093738800594754/3918256753` | `ca-app-pub-5093738800594754/5583681892` |

Both apps show AdMob's normal pre-traffic "Requires review" status — expected, not an error.
Neither is linked to a published App Store/Play Store listing yet.

Wired in: `frontend/.env.local` (all 4 IDs — gitignored, public identifiers, not secrets),
`frontend/android/app/src/main/res/values/strings.xml` (Android App ID),
`frontend/ios/App/App/Info.plist` (iOS App ID). `rewarded-ad-service.ts` already reads the ad unit
IDs from the env vars, falling back to Google's test ad units only when they're unset — which they
no longer are, in this environment.

## Done — SSV callback verified live end-to-end, both platforms

The backend monetization code was committed (`c688f6d`) and deployed to production. Confirmed via
Render's own logs: `Running upgrade 0048 -> 0049, Add predictions.prediction_credits and
predictions.prediction_reward_events`, and the callback endpoint's status changed from a bare 404
to a real `400: "SSV verification failed: callback missing 'signature' parameter"` — the honest
failure mode for a request with no signature, proving the route itself was live.

With the endpoint live, AdMob's "Verify URL" tool was re-run for both ad units, this time sending
a **real ECDSA-signed test callback** (not a plain reachability ping) — both returned **"Success!
Your callback URL has been verified."** This is the strongest verification possible short of a
real device watching a real ad: Google's own infrastructure signed a payload with their real
production key, and `admob_ssv_verifier.py` correctly verified it. Both ad units now have the
callback URL saved under Server-side verification.

One side effect worth knowing: the verification test used a placeholder test user ID
(`00000000-0000-0000-0000-000000000001`) to get a realistic signed payload — this created one real
`prediction_credits` row and one `prediction_reward_events` row in production for that fake UUID.
Harmless (doesn't correspond to any real user, no real user's balance was touched), but if a fully
clean production dataset matters, that row can be deleted directly.

## Still remaining before a real release build

1. **GDPR/consent (spec Phase 12)**: not built in this pass. `rewarded-ad-service.ts` requests
   `npa: true` (non-personalized ads) unconditionally, specifically to avoid needing a real
   consent-collection flow for V1 — this is a deliberate scope boundary, not an oversight. A real
   UMP (User Messaging Platform) consent flow is required before requesting personalized ads.

2. **Apple App Tracking Transparency**: `NSUserTrackingUsageDescription` is present in Info.plist
   (the plugin's documented required key) but `RewardedAdService` never calls
   `AdMob.requestTrackingAuthorization()` — no ATT prompt shows today. Add that call only once a
   real reason to request tracking (e.g. personalized ads) exists.

3. **Privacy Policy / ad disclosure**: `frontend/src/pages/legal/advertising-policy-page.tsx` and
   `cookie-policy-page.tsx` already describe AdMob as a planned "future" integration (written
   before this pass) — both need a copy update now that ads are genuinely configured, not just
   built.

4. **Production frontend env vars**: `.env.local` (local-only, gitignored) now carries the real
   IDs, but the deployed production frontend (Render) does not yet — its own build environment
   needs the same 4 `VITE_ADMOB_*` vars set before a native build against production picks them up.

## What was verified live in this environment

- **All 4 real AdMob resources** (2 App IDs, 2 rewarded ad units) were created live in the user's
  actual AdMob account via browser automation, confirmed via AdMob's own "Ad unit successfully
  created" response screens, not assumed.
- The SSV callback endpoint's full lifecycle was observed live: unreachable (404, code not
  deployed) → deployed (400, honest signature-missing error) → **verified** (Google's real signed
  test callback, correctly validated by `admob_ssv_verifier.py`, on both Android and iOS ad units).
- `npx cap sync android` and `npx cap sync ios` both complete successfully and correctly list
  `@capacitor-community/admob` among 5 registered native plugins for each platform — confirms the
  plugin is correctly wired into both native projects at the Capacitor level.
- The AdMob signature-verification logic is covered by 6 local cryptographic unit tests (a
  locally generated EC keypair, see
  `backend/tests/unit/modules/predictions/test_admob_ssv_verifier.py`) *and* by one real signed
  callback per platform from Google's actual production signing key — both agree.

## What was NOT and could not be verified here

- A compiled Android APK/AAB or iOS IPA (no Android SDK, no Xcode/macOS in this environment).
- A real ad actually rendering on a device or emulator, or a real user completing one (the
  verified SSV callback used a placeholder test user ID, not a real rewarded-ad view).
- Google Play / App Store submission (requires real, paid developer accounts / store listings).
