plugins {
    `java-library`
}

description = "FlowDoc runtime overlay — Spring AOP agent that records execution traces " +
        "over the same node ids the static scanner emits."

// Aligned with the starter's Spring Boot 3.3.x / Spring Framework 6.1.x.
dependencies {
    api(project(":flowdoc-core"))

    // aspectjweaver is `api` on purpose: its presence on the app classpath is what
    // makes Spring Boot's AopAutoConfiguration switch on @AspectJ proxying.
    api("org.aspectj:aspectjweaver:1.9.22")

    implementation("org.springframework:spring-aop:6.1.14")
    implementation("org.springframework:spring-context:6.1.14")

    // RestController lives in spring-web; only needed to reference the annotation type.
    compileOnly("org.springframework:spring-web:6.1.14")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    options.compilerArgs.add("-parameters")
}

tasks.test {
    useJUnitPlatform()
}
