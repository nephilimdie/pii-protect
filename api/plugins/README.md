# Plugin Template

Copy `example.echo` to a new directory, change the manifest name and entrypoint,
then implement `BasePlugin.on_anonymize` and `BasePlugin.on_deanonymize`.

Plugins are opt-in. Set `PLUGIN_AUTOLOAD=true` and point `PLUGIN_DIR` at this
directory only after reviewing the code and permissions.
