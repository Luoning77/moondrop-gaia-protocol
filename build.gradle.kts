import java.util.Properties

plugins {
    alias(libs.plugins.kotlin.jvm)
}

group = "com.moondrop.pudding"
val versionProperties = Properties()
providers.fileContents(layout.projectDirectory.file("version.properties")).asText.get().reader().use {
    versionProperties.load(it)
}
version = versionProperties.getProperty("version")
    ?: error("version.properties must define version")

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(kotlin("test"))
}

kotlin {
    jvmToolchain(17)
}

tasks.test {
    useJUnitPlatform()
}
