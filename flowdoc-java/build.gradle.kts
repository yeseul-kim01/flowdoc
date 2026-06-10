// Root build for the FlowDoc JVM implementation.
// Per-module config lives in each module's build.gradle.kts; only the shared
// coordinates and repositories are declared here.

allprojects {
    group = "io.flowdoc"
    version = "0.1.0-SNAPSHOT"

    repositories {
        mavenCentral()
    }
}
