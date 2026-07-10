rootProject.name = "flowdoc"

// v0.1 — spec + static core. Build plugins arrive in later milestones
// (see docs/flowdoc-기획안.md §14 로드맵).
include("flowdoc-annotations")
include("flowdoc-core")
include("flowdoc-scanner")

// v0.3 — runtime overlay. AOP agent that records execution traces over the same
// node ids the static scanner emits (docs/features/0001-runtime-trace-overlay.md).
include("flowdoc-runtime")

// Swagger-style live viewer: add the starter to a Spring Boot app and the viewer
// + its spec (and live traces) are served at /flowdoc.
include("flowdoc-spring-boot-starter")
