# Plugins

`pii-protect` is intended to support a plugin ecosystem.

## Design goals

- Let customers and partners extend the product without forking the core.
- Allow private, open, and commercial plugins.
- Keep the core product distinct from independently authored extensions.

## Intended rules for plugin authors

- You may build plugins using documented extension points and published APIs.
- You may keep your plugin private, release it for free, or sell it under your own terms.
- You retain ownership of your plugin code, except for any core code copied from this repository that remains subject to the core license.
- A plugin must not embed or redistribute the core product except where the core license explicitly allows it.

## Compatibility expectations

- Plugins should declare the minimum supported `pii-protect` version.
- Plugins should avoid relying on undocumented internal modules.
- Security-sensitive plugins should document what data they read, write, or transmit.

## Distribution paths

- Private install inside a customer deployment.
- Direct distribution by the plugin author.
- Publication through a future `pii-protect` marketplace.

## Marketplace note

Plugins listed in an official marketplace may be subject to additional review, security, and commercial rules (details to be published when the marketplace launches).