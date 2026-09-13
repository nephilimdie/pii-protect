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
signature verification before they can be treated as trusted.

## Distribution paths

- Private install inside a customer deployment.
- Direct distribution by the plugin author.
- Publication through a future `pii-protect` marketplace.

## Marketplace note

Plugins listed in an official marketplace may be subject to additional review, security, and commercial rules (details to be published when the marketplace launches).
