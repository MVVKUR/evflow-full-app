#!/usr/bin/env bash
set -euo pipefail

host="${1:-ev-flow-api.opensoft.id}"

echo "EV-FLOW TLS deployment verification"
echo "host=${host}"
echo "checked_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

https_status="$(curl -sS -o /dev/null -w '%{http_code}' "https://${host}/")"
echo "https_status=${https_status}"
case "${https_status}" in 2*|3*) ;; *) echo "FAIL: HTTPS frontend is unavailable" >&2; exit 1 ;; esac

headers="$(curl -sS -I "http://${host}/")"
http_status="$(printf '%s\n' "${headers}" | awk 'toupper($1) ~ /^HTTP/ {print $2; exit}')"
redirect_location="$(printf '%s\n' "${headers}" | awk 'tolower($1) == "location:" {print $2; exit}' | tr -d '\r')"
echo "http_status=${http_status}"
echo "redirect_location=${redirect_location}"
case "${http_status}" in 301|302|307|308) ;; *) echo "FAIL: HTTP does not redirect" >&2; exit 1 ;; esac
case "${redirect_location}" in https://*) ;; *) echo "FAIL: redirect is not HTTPS" >&2; exit 1 ;; esac

tls13="$(openssl s_client -connect "${host}:443" -servername "${host}" -tls1_3 </dev/null 2>&1)"
printf '%s\n' "${tls13}" | grep -Eq 'TLSv1\.3|Protocol *: TLSv1\.3' || { echo "FAIL: TLS 1.3 was not negotiated" >&2; exit 1; }
echo "tls13=negotiated"
printf '%s\n' "${tls13}" | awk '/subject=|issuer=|Verify return code|Protocol *:|Cipher is / {print "  " $0}'

for legacy in tls1 tls1_1; do
  output="$(openssl s_client -connect "${host}:443" -servername "${host}" "-${legacy}" </dev/null 2>&1 || true)"
  if printf '%s\n' "${output}" | grep -Eq 'Cipher is \(NONE\)|no peer certificate available|alert protocol version|unsupported protocol|handshake failure'; then
    echo "${legacy}=rejected"
  else
    echo "FAIL: ${legacy} was not demonstrably rejected" >&2
    exit 1
  fi
done

echo "result=PASS"
