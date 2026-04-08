# Integration and Extension

This page collects the developer-facing material for extending or integrating `SWC-Studio`.

```{toctree}
:hidden:
:maxdepth: 1

Plugin Demonstration <../PLUGIN_DEMONSTRATION>
Plugin Development <../PLUGIN_DEVELOPMENT>
Architecture <../ARCHITECTURE>
```

## Plugin usage

- [Plugin Demonstration](../PLUGIN_DEMONSTRATION.md)

## Plugin development

- [Plugin Development](../PLUGIN_DEVELOPMENT.md)

## Architecture

- [Architecture](../ARCHITECTURE.md)

The architecture document is especially important if you are adding features. Current design intent is:

- algorithms live in `swcstudio/core`
- task-facing wrappers live in `swcstudio/tools`
- plugins extend tool behavior through the plugin layer
- GUI and CLI remain thin interface wrappers over the tool layer
