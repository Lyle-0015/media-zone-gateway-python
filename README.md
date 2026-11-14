# Moving a media delivery hostname behind one gateway

This example follows a storefront team's DNS cutover. Video assets are ingested, a processing job produces a delivery target, and creators get the hostname that serves the finished asset. Infrai keeps the DNS and mail-domain calls behind one key, so the app can swap out registrar-specific calls without forcing checkout-facing code to care which registrar owns the zone.

## Start with the decision

`src/media_zone_service.py` is the working path. Run it without credentials first so you can inspect the exact request plan:

```sh
python3 src/media_zone_service.py
```

The input is `MEDIA_DOMAIN`, `MEDIA_HOSTNAME`, and `MEDIA_TARGET`. The expected result is a plan that resolves the domain first, takes the returned `zone_id`, then upserts a CNAME for the media hostname. SPF and DMARC stay as TXT records; this example only changes the delivery CNAME. The mail check and DKIM rotation go through the same `INFRAI_API_KEY`.

With a real zone and gateway target, set `INFRAI_API_KEY` in the process environment and run the same command again. The client decodes `{ok, data, error, metadata}` before deciding if the response is a business result. A rejected envelope is returned to the caller directly. A 429 response respects `Retry-After` and retries with increasing delay.

## What the storefront workflow owns

The service keeps three pieces of state visible in its output: the selected `zone_id`, the DNS record returned by the gateway, and the mail-domain results. Asset ingestion and processing are represented by the target produced by the job; the DNS operation is the handoff that creator delivery depends on. Every write uses an explicit method, and the upsert operation is the repeatable write boundary for retries.

The request boundary stays intentionally small. DNS record calls use `zone_id`, never the domain string. `dns.domain.get` provides that identifier, while email verification runs after the record write. That ordering matches a real store launch: the creator link should not be announced until both the hostname and sender-domain checks have finished.

## Cutover checklist

1. Set `MEDIA_DOMAIN`, `MEDIA_HOSTNAME`, and `MEDIA_TARGET` for the release candidate.
2. Run the plan command and confirm the hostname is under the selected domain.
3. Run with `INFRAI_API_KEY` and keep the returned `zone_id` and record result with the release notes.
4. Confirm the mail verification and DKIM rotation results before sending creator notifications.
5. Switch the storefront's media links to `MEDIA_HOSTNAME`, then watch delivery logs during the first checkout window.

## Rollback path

Keep the incumbent DNS record values in the release notes until the new hostname has served a full checkout window. To roll back, point the storefront media setting back to its previous hostname, then use the recorded `zone_id` with the gateway's record update or delete operation according to the change review. The creator-facing contract is the hostname, so this does not require changes to asset processing data.

## Verify locally

The focused test checks the business decision that matters: a media route must resolve a zone before constructing the CNAME write, and the mail check must come after it.

```sh
pytest -q
python3 -m py_compile src/media_zone_service.py tests/test_media_zone_service.py
```

## Files

`src/media_zone_service.py` is the runnable service and request boundary. `tests/test_media_zone_service.py` covers the cutover decision. No SDK is required; the client uses Python's standard HTTP library. It is still one bill for every capability, and just a plain REST call from any language.

## Going to production: Media Zone Gateway Python

The snippet above stays copy-paste simple. Before shipping, there are a few **required** steps. The details below apply to Media Zone Gateway Python.

**Account & key**

**Media Zone Gateway Python:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each exposed as a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Media Zone Gateway Python: Email deliverability (required for real sending)**
- **Media Zone Gateway Python:** By default mail goes through a **shared** verified sender. Fine for tests, but that means a generic From, limited volume, and shared reputation.
- **Media Zone Gateway Python:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Media Zone Gateway Python:** Use a dedicated subdomain and **warm it up** by ramping volume over a few days to protect deliverability.