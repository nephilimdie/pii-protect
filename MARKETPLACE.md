# Marketplace Principles

This document describes the intended rules for a future `pii-protect` plugin marketplace.

## Goals

- Make it easy to discover useful plugins.
- Allow plugin authors to monetize their work if they want to.
- Give operators a safer distribution channel than ad hoc binaries or scripts.

## Publisher model

- Publishers may offer free or paid plugins.
- Publishers may distribute plugins privately outside the marketplace if they prefer.
- Listing in the official marketplace may require identity verification and review.

## Review expectations

- Plugin metadata must accurately describe capabilities and permissions.
- Plugins must not silently exfiltrate data.
- Plugins must not disable or weaken core security controls without a clear operator action.
- Plugins must declare external services, network destinations, and sensitive scopes where applicable.

## Commercial principles

- Paid plugins may be sold by their authors under their own license terms.
- The marketplace operator may charge listing fees, transaction fees, or subscription fees under separate terms.
- The marketplace does not transfer ownership of plugin IP to the operator unless explicitly agreed.

## Enforcement

- The marketplace operator may refuse, suspend, or remove plugins that violate security, legal, or policy requirements.
- Marketplace access may be limited for plugins that impersonate the core product or create brand confusion.

## Relationship to the core license

The marketplace rules are separate from the core repository license. The core license governs the repository itself. Marketplace participation would be governed by additional publisher and customer terms.