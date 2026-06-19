# FlowDoc

> **Swagger for the inside of your backend.**
> Not the external API contract — what *actually happens after a request comes in*:
> which service's which function it passes through, where the transaction boundaries
> are, what's guarded for concurrency, and what fires asynchronously after commit.

FlowDoc analyzes backend source and draws **function call flows, transaction
boundaries, concurrency guards, and async post-processing** as an interactive,
Swagger-UI-like view. Anything that can be pulled from code is pulled automatically;
only the intent a static parser cannot know is declared with small annotations.

Two collectors built in parallel — **Spring Boot** (kys) and **FastAPI** (jch) — emit the
**same** language-neutral spec into the **same** UI. Same feature set, different frameworks.

📖 사용법: [docs/usage.md](docs/usage.md) · 🤝 팀 분담: [docs/collaboration.md](docs/collaboration.md) · 📄 Full design: [docs/flowdoc-기획안.md](docs/flowdoc-기획안.md) · 💡 시각화 아이디어: [docs/ideas.md](docs/ideas.md)

---

## How it works (spec-first)

A language-neutral JSON spec sits in the middle. Collectors *produce* it; the UI *reads* it —
exactly like the OpenAPI-spec / Swagger-UI split.

```
[Spring Boot scanner — kys] ─┐
[FastAPI scanner — jch]      ─┼─→  [shared spec (JSON)]  ─→  [FlowDoc UI (HTML)]
[Runtime agent (later)]      ─┘         single source of truth
```

The spec is the **contract** between the two collectors; the UI is **shared** and
language-neutral. Ownership and feature-parity mapping: [docs/collaboration.md](docs/collaboration.md).

The guiding rule (design §5): **never make a human write what the parser can read; ask
for declaration only where intent/identity/meaning is not statically knowable.** A call's
*existence* is detected automatically — only its *meaning* (`@FlowEntry`, `@Guarded`, …)
is declared.

## Repository layout

```
spec/                     # JSON Schema — the single source of truth, language-neutral
ui/                       # shared HTML viewer (consumes the spec)
flowdoc-java/             # Spring Boot collector — kys (Gradle multi-module)
  flowdoc-annotations/      # @FlowEntry, @Guarded, … that user code imports
  flowdoc-core/             # spec model (records) + JSON (de)serialization
  flowdoc-scanner/          # static scanner: JavaParser + SymbolSolver → spec
  flowdoc-spring-boot-starter/  # serves the viewer + spec live at /flowdoc (Swagger-style)
flowdoc-python/           # FastAPI collector — jch (ast-based, same spec, /flowdoc router)
examples/sample-shop/     # minimal self-contained demo (stand-in annotations)
examples/coupon-rush/     # real Spring Boot app: scan → flowdoc.json → live /flowdoc
poc/                      # original UI prototype
docs/                     # design docs
```

`flowdoc-spring-boot-starter` already serves the viewer + a prebuilt spec live at
`/flowdoc` (add the dependency, scan into resources, done). Later milestones add
`flowdoc-agent` (runtime AOP) and `flowdoc-gradle-plugin` / `flowdoc-maven-plugin` to
generate the spec automatically at build time — see the roadmap.

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

The scanner emits one node per method and one edge per call it can place: internal calls
resolve to scanned methods, and calls into a `@Repository` / Spring Data repository (or a
`@FlowExternal` type) are drawn as **boundary nodes** — only genuinely unknown targets are
dropped, never guessed. It also captures `@FlowEntry` sequences, `@Guarded` guards,
`@Transactional` markers, async edges (`@Async`), and per-node descriptions (Javadoc or
`@FlowDoc`).

For a **real Spring Boot app** wired end-to-end — scan → spec → live viewer at `/flowdoc` —
see [examples/coupon-rush](examples/coupon-rush/):

```bash
cd ../examples/coupon-rush && ./gradlew bootRun   # open http://localhost:8080/flowdoc
```

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
| **v0.1** ✅ | JSON spec + static core (nodes/edges/`auto` + `@FlowEntry`/`@Transactional`/`@Guarded`), UI structure view |
| **v0.2** 🔄 | Javadoc → docs ✅, `@FlowExternal`/repository boundary nodes ✅, async edges ✅, live `/flowdoc` starter ✅ · _remaining:_ full single-impl/`@FlowResolves`, `@FlowIgnore`, Gradle/Maven plugins, accessor-noise filtering |
| **v0.3** | Runtime overlay (Spring AOP + `TransactionSynchronization`), UI trace view |
| **v0.4** | Event publish ↔ handler linking, ambiguity resolution, multi-module boundaries |
| **v1.0** | Stabilization, packaging |
| **parallel track** | **FastAPI collector** (jch) — same spec & UI, feature parity with the Spring side ([docs/collaboration.md](docs/collaboration.md)) |

Currently mid **v0.2** on the Spring side (kys): the static scanner resolves internal +
repository/external calls, async, guards, transactions, and descriptions; the
`flowdoc-spring-boot-starter` serves the viewer live at `/flowdoc`. The FastAPI collector
(jch) starts in parallel against the same spec contract.

## License

[Apache-2.0](LICENSE).
