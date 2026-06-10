# FlowDoc UI

A single-file viewer that renders a `flowdoc.json` spec — the viewer half of FlowDoc.
It is **language-neutral**: it consumes the [shared spec](../spec/flowdoc-0.1.schema.json)
and never knows whether the producer was the Java scanner or (later) the Python one.

No build step, no dependencies. Just [`index.html`](index.html) + a spec.

## Run it

**Quickest — serve the folder** (auto-loads `./flowdoc.json`):

```bash
cd ui
python3 -m http.server 8080
# open http://localhost:8080
```

A demo spec ([`flowdoc.json`](flowdoc.json), copied from the sample-shop example) is already
here, so the above shows a real flow immediately.

**Or just open the file** — double-click `index.html`. Browsers block `fetch()` on
`file://`, so it opens to a drop zone: **drag a `flowdoc.json` onto it** (or click to pick).

**Point at any spec** via query param: `index.html?spec=/path/or/url/to/flowdoc.json`.

You can also swap specs anytime from the sidebar ("다른 flowdoc.json 열기").

## What it draws

- **Sidebar** — spec metadata, the list of `@FlowEntry` sequences (click to switch), legend.
- **Structure view** — the call tree from the selected entry point, following resolved edges:
  - monospace signature `Owner.method(p: Type): Return`
  - badges: route (`POST /orders`), `@Transactional`, `@Guarded` (red), `@Async` (teal),
    `external` (blue), `@Repository`, and `↻ 순환` on cycles
  - `@Transactional` nodes wrap their synchronous calls in an **amber tx rail**
    (`tx begin … commit`); `@Async` children render **outside** the rail (dashed teal)
  - click any row to expand `auto` chips (params / return / annotations / location) and the
    `doc` description
- Cycles are detected (`↻`) and depth is capped so recursive graphs stay finite.

## Generate a spec to view

```bash
cd ../flowdoc-java
./gradlew :flowdoc-scanner:run \
  --args="/path/to/your/src/main/java /path/to/ui/flowdoc.json"
```

Then reload the UI. Note: the structure view is organized around `@FlowEntry` sequences —
if a codebase has none yet, the scanner emits nodes/edges but no sequences, and the UI says
so. Add `@FlowEntry("some-tag")` to an entry method (controller, listener, …) to get a flow.
