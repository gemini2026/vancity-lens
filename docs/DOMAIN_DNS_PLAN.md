# INFRA-002 Domain and DNS Plan

Domain owner: Cloudflare zone `vancitylense.com`

## Hostname Plan

| Hostname | Purpose | Target | Cloudflare Proxy |
|---|---|---|---|
| `vancitylense.com` | Marketing/root redirect | Redirect -> `app.vancitylense.com` | Proxied |
| `www.vancitylense.com` | Legacy/root alias | Redirect -> `app.vancitylense.com` | Proxied |
| `app.vancitylense.com` | Primary frontend | GKE frontend ingress/LB IP | Proxied |
| `api.vancitylense.com` | Public API | GKE API ingress/LB IP | DNS-only during cert bootstrap, then Proxied |
| `staging.vancitylense.com` | Staging frontend/API gateway | Staging ingress/LB IP | DNS-only initially |

## TLS and Proxy Sequence

1. Create A/AAAA/CNAME records in Cloudflare via Terraform.
2. For `api` start in DNS-only mode until origin certificate path is healthy.
3. Validate origin TLS and app health checks.
4. Switch `api` to proxied and enable strict WAF/rate limits.

## DNS Change Policy

- All DNS and Cloudflare policy changes must be done in Terraform.
- No manual dashboard edits except break-glass incidents.
- Break-glass edits must be backported to Terraform within 24 hours.
