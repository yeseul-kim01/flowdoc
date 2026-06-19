plugins {
    `java-library`
}

description = "FlowDoc Spring Boot starter — serves the viewer + spec at /flowdoc, Swagger-style."

// Aligned with the example app's Spring Boot 3.3.x (Spring Framework 6.1.x).
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure:3.3.5")
    implementation("org.springframework:spring-webmvc:6.1.14")

    compileOnly("org.springframework.boot:spring-boot-configuration-processor:3.3.5")
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor:3.3.5")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    options.compilerArgs.add("-parameters")
}

// Single source of truth for the viewer: bundle the shared UI into the jar at build
// time instead of committing a second copy. The repo's ui/ sits beside flowdoc-java/.
tasks.processResources {
    from("${rootProject.projectDir}/../ui/index.html") {
        into("flowdoc")
    }
}
