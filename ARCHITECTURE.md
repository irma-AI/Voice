# Architecture

The map an agent needs before changing structure: the layers, which way dependencies point, and the one interface each cross-cutting concern goes through. Be strict about these boundaries and loose about how code inside a layer is written.

## Layers

None yet: each layer is written here when its first code lands.

<!-- One line per layer, lowest first: its name and what it holds. Example for a web app: types, config, data access, services, API, UI. Paths and allowed imports live only in scripts/checks/layers.json. -->

## Dependency direction

Dependencies point down the list: a layer imports only the layers its `may_import` names in `scripts/checks/layers.json`, and the `layers` guard fails any other import.

## Cross-cutting concerns

Each concern has one interface, and code reaches it only through that interface:

<!-- One line each: auth, logging and telemetry, feature flags, configuration, and any other concern code everywhere needs. Name the module or function. -->

- Auth for the web Channel: `voice.auth.BasicAuth`, the one login in front of every route (`voice/web.py` adds it; it needs `VOICE_PASSWORD`).
