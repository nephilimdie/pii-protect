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

## Local package contract

Each plugin lives in one directory below `PLUGIN_DIR` and contains a validated
`plugin.json` plus a Python entrypoint:

```json
{
  "name": "acme.ocr",
  "version": "1.0.0",
  "compatibility": ">=1.0,<2.0",
  "permissions": ["read_text", "write_entities"],
  "entrypoint": "plugin:AcmeOcrPlugin"
}
```

The class must extend `BasePlugin`. Loading is disabled by default. An operator
must set `PLUGIN_AUTOLOAD=true` and `PLUGIN_DIR=/absolute/path/plugins`; the
loader rejects invalid names, missing entrypoints and paths escaping the plugin
directory. Review and checksum packages before enabling them. The admin API
lists loaded plugins and can disable one without changing files.

For local package installation use `PluginPackageInstaller` with a SHA-256
published out of band. It rejects checksum mismatches, archives with more than
one manifest, path traversal and overwriting an existing plugin. A checksum is
integrity protection only; marketplace packages still require detached
signature verification before they can be treated as trusted. The installer
accepts an Ed25519 signature and PEM public key for that deployment mode and
verifies the archive bytes before extraction.

## Distribution paths

The repository includes `api/plugins/example.echo` as a minimal compatibility
template. It is not loaded unless `PLUGIN_AUTOLOAD=true` is explicitly set.

- Private install inside a customer deployment.
- Direct distribution by the plugin author.
- Publication through a marketplace compatible with the optional core client.

## Optional marketplace client

Self-hosted administrators can browse and install packages from a configured
marketplace without adding a cloud dependency to the engine:

```text
MARKETPLACE_URL=https://marketplace.example
MARKETPLACE_TOKEN=optional-entitlement-token
MARKETPLACE_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----..."
MARKETPLACE_MAX_PACKAGE_BYTES=50000000
PLUGIN_DIR=/absolute/path/plugins
PLUGIN_AUTOLOAD=false
```

The admin API exposes `GET /v1/admin/marketplace/plugins` and
`POST /v1/admin/marketplace/plugins/install` with `{ "name": "plugin.name" }`.
The client only downloads packages from the configured HTTPS origin, verifies
the catalog checksum and, when a public key is configured, verifies the
detached Ed25519 signature before extraction. Installation never autoloads a
plugin: restart with `PLUGIN_AUTOLOAD=true` only after reviewing its manifest,
permissions and source. The marketplace service remains responsible for
accounts, payment, entitlement and package hosting.

## Marketplace note

Plugins listed in an official marketplace may be subject to additional review, security, and commercial rules (details to be published when the marketplace launches).
