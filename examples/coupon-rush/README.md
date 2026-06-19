# coupon-rush — a real Spring Boot target for FlowDoc

A minimal but **genuine** Spring Boot app (real `spring-boot-starter-web` + `data-jpa`,
real `@RestController` / `@Service` / `@Transactional` / `@Async` / JPA), used to drive
the FlowDoc scanner end-to-end. Unlike `sample-shop`, nothing here is a stand-in.

## The flow

First-come coupon issuance:

```
POST /api/campaigns/{id}/coupons   @FlowEntry("issue-coupon")
  CouponController#issue
    └─ CouponService#issue                 @Transactional   (tx boundary)
         ├─ reserveStock                    @Guarded(coupon-stock, 1)
         │    └─ decrement → Campaign#decrementRemaining
         ├─ couponRepository.save(...)       (JPA — see limitation 1)
         └─ NotificationService#notifyIssued @Async          (fires post-commit)
              ├─ render
              └─ dispatch
```

## Scan it

The scanner only **parses source** — it does not compile this app and needs none of its
Spring jars on the classpath. Emit the spec straight into the app's resources so the live
viewer (below) can serve it:

```bash
cd ../../flowdoc-java
./gradlew :flowdoc-scanner:run \
  --args="$(pwd)/../examples/coupon-rush/src/main/java \
          $(pwd)/../examples/coupon-rush/src/main/resources/flowdoc.json"
```

Produces **12 nodes, 9 edges, 1 guard, 1 sequence** (validates against
`spec/flowdoc-0.1.schema.json`).

## View it — Swagger-style, from the running app

This app depends on `flowdoc-spring-boot-starter`, so the viewer + spec are served live:

```bash
./gradlew bootRun     # in examples/coupon-rush
# then open http://localhost:8080/flowdoc
```

- `GET /flowdoc`               → redirect to `/flowdoc/`
- `GET /flowdoc/`              → the shared HTML viewer
- `GET /flowdoc/flowdoc.json`  → the prebuilt spec the viewer fetches (`classpath:flowdoc.json`)

The spec is **prebuilt at scan time** (the step above), not generated at runtime — a running
jar has no source to parse. Re-run the scanner and restart to refresh.

Prefer the standalone viewer? `cp src/main/resources/flowdoc.json ../../ui/ && cd ../../ui &&
python3 -m http.server 8080`.

## What the full flow shows

From the `@FlowEntry` the structure view now renders the whole flow — transaction rail,
guard, async post-processing, and external calls all reachable from the entry:

```
CouponController#issue          @PostMapping @FlowEntry
  CouponService#issue           @Transactional         ← amber tx rail
    reserveStock                @Guarded(coupon-stock) ← red guard badge
      CampaignRepository#findById   @Repository        ← external/data boundary
      decrement → Campaign#decrementRemaining
    CouponRepository#save           @Repository        ← external/data boundary
    NotificationService#notifyIssued  @Async (async edge) ← outside the rail
      render · dispatch
```

### Fixed while building this (real scanner work)

- **Controller → service edge no longer drops.** `couponService.issue(id, request.userId())`
  failed full resolution because the record accessor `userId()` is an unresolvable argument,
  which threw away the *whole* call. The scanner now falls back to resolving the **receiver
  type + method name** (no argument resolution needed) — recovering the edge without guessing.
- **External calls are drawn.** Calls into a `@Repository` / Spring Data repository (or a
  `@FlowExternal` type) become boundary nodes with a `@Repository` badge instead of vanishing.
  We don't fabricate the inherited signature — just the known boundary.
- **`@Async` edges carry `callType: "async"`**, and **duplicate edges are deduplicated**.
- **Descriptions, Swagger-style.** A node's `declared.description` + per-param docs now come
  from **Javadoc** automatically (`CouponService#issue`, `reserveStock`), or from an explicit
  **`@FlowDoc(summary, params = @Param(...))`** when you want to author it (`CouponController#issue`).
  Expand a row in the viewer to see them. `@FlowDoc` wins; Javadoc fills the rest.

### Still open (next roadmap candidates)

1. **Trivial accessors are flow nodes.** `Coupon#getCode()`, `Campaign#getRemaining()` show
   up as steps — graph noise that should be filtered or collapsed.
2. **Class-level `@RequestMapping` is lost.** Only the method's `@PostMapping`
   (`/{campaignId}/coupons`) is captured; the `/api/campaigns` prefix isn't, so the route
   badge is partial.
3. **Disconnected nodes.** `CouponRushApplication#main` is emitted but belongs to no flow.
4. **Single-impl interface resolution** (v0.2) — today interface-typed dependencies only link
   if a unique method name matches; ambiguous overloads are still refused rather than ranked.
