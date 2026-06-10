# FlowDoc UI

The single-page viewer that renders a `flowdoc.json` spec — the "Swagger UI" of FlowDoc.
It is **language-neutral**: it consumes the [shared spec](../spec/flowdoc-0.1.schema.json)
and never knows whether the producer was the Java scanner or (later) the Python one.

## Status

The visual direction is fixed by the prototype at
[../poc/ui/example_v0.1.html](../poc/ui/example_v0.1.html). The next step (roadmap v0.1)
is to wire that prototype to consume a real `flowdoc.json` instead of inline data.

## Views

- **Structure view** — indented call tree from the entry point; amber transaction rail,
  red semaphore-guard badges, teal async badges, blue external badges. Clicking a row
  expands `auto` chips (params / returns / annotations / location) and `doc` chips.
- **Trace view** (runtime milestone) — the same tree with the real execution replayed.

## Try it with the sample spec

A real spec produced by the scanner lives at
[../examples/sample-shop/flowdoc.json](../examples/sample-shop/flowdoc.json).
Regenerate it with:

```bash
cd flowdoc-java
./gradlew :flowdoc-scanner:run --args="$(pwd)/../examples/sample-shop/src/main/java $(pwd)/../examples/sample-shop/flowdoc.json"
```
