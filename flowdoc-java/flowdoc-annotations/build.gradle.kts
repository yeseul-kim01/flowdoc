plugins {
    `java-library`
}

description = "FlowDoc declaration annotations (@FlowEntry, @Guarded, …) that user code imports."

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    options.compilerArgs.add("-parameters")
}
