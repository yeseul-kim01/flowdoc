plugins {
    application
}

description = "FlowDoc static scanner — JavaParser + SymbolSolver source analysis that emits the shared spec."

dependencies {
    implementation(project(":flowdoc-core"))
    implementation("com.github.javaparser:javaparser-symbol-solver-core:3.28.2")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

application {
    mainClass.set("io.flowdoc.scanner.Main")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    options.compilerArgs.add("-parameters")
}

tasks.test {
    useJUnitPlatform()
}
