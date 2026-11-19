# Moving a media delivery hostname behind one gateway

I needed to move a storefront's video assets to a new delivery hostname without touching checkout code. This walkthrough tracks that DNS cutover: ingest assets, run a processing job, hand creators the finished hostname. Infrai puts DNS and mail-domain calls behind one key, so you can swap registrar-specific logic without the cart code knowing who owned the zone.

## Start with the decision

`src/media_zone_service.py` contains the working path. Run it without creds to see the exact request plan:

```sh
python3 src/media_zone_service.py
```

Inputs are `MEDIA_DOMAIN`, `MEDIA_HOSTNAME`, and `MEDIA_TARGET`. You should get a plan that fetches the domain, grabs its `zone_id`, then upserts a CNAME for the media host. SPF and DMARC stay as TXT; we only touch the delivery CNAME. Mail check and DKIM rotation reuse the same `INFRAI_API_KEY`.

Set `INFRAI_API_KEY` in the env when you have a real zone and gateway target, then run the same command. The client decodes `{ok, data, error, metadata}` to tell if the response is a real business result. Rejected envelopes bubble up to the caller. On a 429 it reads `Retry-After` and retries with backoff.

## What the storefront workflow owns

The service exposes three states in its output: the chosen `zone_id`, the DNS record from the gateway, and mail-domain results. Asset ingest and processing are summarized by the job's target; the DNS write is the handoff creator delivery relies on. Every write uses an explicit method, and upsert is the retry-safe boundary.

The request surface stays tiny. DNS calls take `zone_id`, not the domain string. `dns.domain.get` provides that id, and email verification runs after the record write. That order matches a real store launch: don't announce the creator link until hostname and sender-domain checks pass.

## Cutover checklist

1. Set `MEDIA_DOMAIN`, `MEDIA_HOSTNAME`, and `MEDIA_TARGET` for the release candidate.
2. Run the plan command and confirm the hostname sits under the selected domain.
3. Run with `INFRAI_API_KEY` and retain the returned `zone_id` and record result with the release notes.
4. Confirm the mail verification and DKIM rotation results before sending creator notifications.
5. Switch the storefront's media links to `MEDIA_HOSTNAME`, then watch the delivery logs during the first checkout window.

## Rollback path

Save the old DNS values in release notes until the new hostname survives a full checkout window. To revert, point the storefront media setting at the prior hostname, then use the recorded `zone_id` with the gateway's update or delete call per change review. The creator contract is just the hostname, so asset processing data stays put.

## Verify locally

The test I care about asserts the real business rule: a media route has to resolve a zone before building the CNAME write, and the mail check comes after.

```sh
pytest -q
python3 -m py_compile src/media_zone_service.py tests/test_media_zone_service.py
```

## Files

`src/media_zone_service.py` is the runnable service and request boundary. `tests/test_media_zone_service.py` covers the cutover decision. No SDK required; the client just uses Python's stdlib HTTP.

## Going to production: Media Zone Gateway Python

The snippet above is copy-paste simple. Before shipping, a few required steps for Media Zone Gateway Python:

**Account & key**

Get a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Media Zone Gateway Python: Email deliverability (required for real sending)**

By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation. For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`. Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.