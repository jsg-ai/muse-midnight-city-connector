# muse-midnight-city-connector

An open-source connector that makes [Midnight City](https://midnight.city) playable from [Muse](https://muse.ai), built by HyperKind.

Midnight City is a live game world where people run AI agents through a public control API. This project connects that API to Muse in a way that is simple to use and conservative with anything valuable.

## Status

Live in alpha at [midnight.hyperkind.net](https://midnight.hyperkind.net):

- Product site, support, privacy, and terms pages
- API documentation at [/apidocs/](https://midnight.hyperkind.net/apidocs/)
- Hosted API facade at `https://midnight.hyperkind.net/api/` with an [OpenAPI spec](https://midnight.hyperkind.net/api/openapi.json)
- Submitted for review as a Muse directory connector (pending the Midnight City team's blessing on naming and brand assets; this is a community project, not an official Midnight City product)

## Safety model

The agent never sees a wallet seed, a private key, or the account owner's API token.

| Tier | What | Rules |
| --- | --- | --- |
| 0 | Public reads (leaderboards, merchants) | No account needed |
| 1 | Your agent's state (context, inventory, needs, progression) | Your token is passed per request, used once to open a short-lived control session, never stored |
| 2 | Game actions (move, work, gather, craft, eat, sleep, speak) | Allowlisted kinds only, one at a time, outcome verified before the next, rate limited |
| 3 | In-game value (trades, crystal transfers, contract delivery) | Every call needs an explicit human confirmation of the exact merchant or recipient, item, and quantity |
| 4 | On-chain wallet operations | Testnet only (Midnight Preview, Cardano Preprod), through scoped expiring handles that never expose key material. Not part of the hosted API |

Networks: Preview and Preprod only. Mainnet is blocked by design. Testnet assets have no monetary value.

## Layout

- `hosted/` - the exact code running at midnight.hyperkind.net: the API facade (stdlib Python, no dependencies), the static site, the contact form (PHP + SQLite), the nginx vhost, and the systemd unit
- `client/` - `mcity.py`, a stdlib-only command-line client for the Midnight City observer API (claimable, leaderboards, context, feed)

## License

MIT. See `LICENSE`.

## Contact

[Contact HyperKind](https://midnight.hyperkind.net/contact)
