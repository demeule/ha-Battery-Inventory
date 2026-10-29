# Security

Battery Inventory runs inside Home Assistant and is only reachable through Home Assistant's own login (ingress):
the server refuses any request that does not come from the Home Assistant proxy.

If you find a security problem, please **do not open a public issue**. Use GitHub's
["Report a vulnerability"](https://github.com/demeule/ha-Battery-Inventory/security/advisories/new) button on the Security tab,
and describe what you found. I will answer as soon as I can.
