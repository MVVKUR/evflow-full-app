# Epic 2 TLS Deployment Verification

Run from `backend-ev-flow` against the deployed frontend/API origin:

```sh
bash scripts/verify_tls.sh ev-flow-api.opensoft.id
```

The check fails unless all of the following are observed from the deployed service:

- The HTTPS frontend returns a successful or redirect response.
- Plain HTTP redirects to an HTTPS URL.
- An OpenSSL client negotiates TLS 1.3.
- TLS 1.0 and TLS 1.1 handshakes are rejected.
- The peer certificate verifies successfully and its subject/issuer are recorded.

Store each release's complete output in `docs/deployment-evidence/` with the UTC date. Evidence is environment-specific and must be regenerated after certificate or reverse-proxy changes.
