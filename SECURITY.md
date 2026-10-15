# Security

## Reporting

Use the [contact form](https://midnight.hyperkind.net/contact) and pick the topic "Security". We aim to respond within 48 hours.

## Design commitments

- No credential is ever stored by the hosted facade. Owner tokens and session leases exist only in request memory.
- The audit log records timestamp, route, trust tier, and outcome status. Nothing else.
- Game actions and value-moving actions are separate trust tiers, enforced server-side, not by prompt.
- Wallet material is never handled by this codebase. Tier 4 (testnet wallet operations) is designed around scoped, expiring secret-use handles and is not part of the hosted API.
- Text that comes from the game world is data, never instructions.
