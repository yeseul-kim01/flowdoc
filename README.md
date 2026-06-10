# FlowDoc

> **Swagger for the inside of your backend.**
> Not the external API contract — what *actually happens after a request comes in*:
> which service's which function it passes through, where the transaction boundaries
> are, what's guarded for concurrency, and what fires asynchronously after commit.

FlowDoc analyzes backend source and draws **function call flows, transaction
boundaries, concurrency guards, and async post-processing** as an interactive,
Swagger-UI-like view. Anything that can be pulled from code is pulled automatically;
only the intent a static parser cannot know is declared with small annotations.

Java / Spring Boot first, **Python planned** — both emit the same language-neutral spec.

📄 Full design: [docs/flowdoc-기획안.md](docs/flowdoc-기획안.md)

---

## How it works (spec-first)

A language-neutral JSON spec sits in the middle. Collectors *produce* it; the UI *reads* it —
exactly like the OpenAPI-spec / Swagger-UI split.

```
[Static scanner (Java)] ─┐
[Runtime agent (Java)]   ─┼─→  [shared spec (JSON)]  ─→  [FlowDoc UI (HTML)]
[Python scanner (later)] ─┘         single source of truth
```

The guiding rule (design §5): **never make a human write what the parser can read; ask
for declaration only where intent/identity/meaning is not statically knowable.** A call's
*existence* is detected automatically — only its *meaning* (`@FlowEntry`, `@Guarded`, …)
is declared.

## Repository layout

```
spec/                     # JSON Schema — the single source of truth, language-neutral
ui/                       # shared HTML viewer (consumes the spec)
flowdoc-java/             # Gradle multi-module JVM implementation
  flowdoc-annotations/      # @FlowEntry, @Guarded, … that user code imports
  flowdoc-core/             # spec model (records) + JSON (de)serialization
  flowdoc-scanner/          # static scanner: JavaParser + SymbolSolver → spec
flowdoc-python/           # (later) ast-based scanner emitting the same spec
examples/sample-shop/     # demo source + a generated flowdoc.json
poc/                      # original UI prototype
docs/                     # design docs
```

Later milestones add `flowdoc-agent` (runtime AOP), `flowdoc-gradle-plugin` /
`flowdoc-maven-plugin`, and `flowdoc-spring-boot-starter` — see the roadmap.

## Quickstart

Requires a JDK 21+ (the build targets Java 21). Gradle is provided via the wrapper.

```bash
cd flowdoc-java

# build everything + run tests
./gradlew build

# scan a source tree and emit a spec
./gradlew :flowdoc-scanner:run \
  --args="$(pwd)/../examples/sample-shop/src/main/java $(pwd)/../examples/sample-shop/flowdoc.json"
```

The scanner emits one node per method, one edge per **resolvable internal call**
(unresolved/external calls are dropped, never guessed), plus `@FlowEntry` sequences,
`@Guarded` guards, and `@Transactional` markers. See the result in
[examples/sample-shop/flowdoc.json](examples/sample-shop/flowdoc.json).

## Annotations (what you declare)

```java
@FlowEntry("place-order")                              // a sequence entry point + its name
@Guarded(resource = "inventory", permits = 1)          // what a semaphore actually protects
@FlowResolves(InventoryServiceImpl.class)              // pick the impl when a call is ambiguous
@FlowLink(event = OrderPlaced.class, to = "Handler#on")// connect a publish to its handler
@FlowExternal   @FlowIgnore   @FlowDoc(summary = "…")  // boundary / noise control / docs
```

Standard annotations (`@Transactional`, `@PostMapping`, `@Async`, `@Repository`, …) are
**read** — never re-declared.

## Roadmap

| Milestone | Scope |
|---|---|
| **v0.1** | JSON spec + static core (nodes/edges/`auto` + `@FlowEntry`/`@Transactional`/`@Guarded`), UI structure view |
| **v0.2** | Javadoc → docs, single-impl interface resolution, `@FlowExternal`/`@FlowIgnore`/`@FlowResolves`, Gradle/Maven plugins |
| **v0.3** | Runtime overlay (Spring AOP + `TransactionSynchronization`), UI trace view |
| **v0.4** | Event publish ↔ handler linking, ambiguity resolution, multi-module boundaries |
| **v1.0** | Stabilization, packaging, live `/flowdoc` endpoint, Python collector |

Currently at **v0.1**: spec model + a working static scanner.

## License

[Apache-2.0](LICENSE).
