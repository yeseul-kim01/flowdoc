rootProject.name = "flowdoc"

// v0.1 — spec + static core. Runtime agent / build plugins arrive in later
// milestones (see docs/flowdoc-기획안.md §14 로드맵).
include("flowdoc-annotations")
include("flowdoc-core")
include("flowdoc-scanner")

// Swagger-style live viewer: add the starter to a Spring Boot app and the viewer
// + its spec are served at /flowdoc.
include("flowdoc-spring-boot-starter")
